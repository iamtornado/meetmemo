from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.tasks.celery_app import celery_app
from app.tasks.pipeline_helpers import notify_meeting

logger = logging.getLogger(__name__)


DEFAULT_SUMMARY_TEMPLATE = """You are a meeting summary assistant. Given the following meeting transcript with speaker labels, generate a structured summary.

Transcript:
{transcript}

Generate a JSON response with exactly this structure:
{{
    "title": "A concise meeting title",
    "date": "Meeting date if mentioned, otherwise null",
    "attendees": [
        {{"name": "Speaker Name or Speaker_XX", "is_guest": false}}
    ],
    "key_points": [
        {{"topic": "Topic area", "description": "Detailed point", "importance": 3}}
    ],
    "decisions": [
        {{"description": "What was decided", "made_by": "Who proposed it", "consensus": true}}
    ],
    "action_items": [
        {{"description": "What needs to be done", "assignee": "Who is responsible", "status": "pending"}}
    ],
    "next_agenda": "Topics for next meeting",
    "additional_notes": "Any other relevant information"
}}
"""

MAP_CHUNK_TEMPLATE = """You are summarizing part {part} of {total} of a long meeting transcript.
Extract only facts stated in THIS portion. Output valid JSON with this structure (use empty arrays/strings when none):
{{
    "title": "short topic for this portion or empty string",
    "date": null,
    "attendees": [{{"name": "...", "is_guest": false}}],
    "key_points": [{{"topic": "...", "description": "...", "importance": 3}}],
    "decisions": [{{"description": "...", "made_by": "...", "consensus": true}}],
    "action_items": [{{"description": "...", "assignee": "...", "status": "pending"}}],
    "next_agenda": "",
    "additional_notes": "..."
}}

Transcript portion:
{transcript}
"""

REDUCE_TEMPLATE = """You are merging {count} partial summaries of the SAME meeting into one final structured summary.
Deduplicate overlapping points, combine action items and decisions, and write a coherent overall title.
Output valid JSON with exactly this structure:
{{
    "title": "A concise meeting title",
    "date": "Meeting date if mentioned, otherwise null",
    "attendees": [{{"name": "...", "is_guest": false}}],
    "key_points": [{{"topic": "...", "description": "...", "importance": 3}}],
    "decisions": [{{"description": "...", "made_by": "...", "consensus": true}}],
    "action_items": [{{"description": "...", "assignee": "...", "status": "pending"}}],
    "next_agenda": "Topics for next meeting",
    "additional_notes": "Any other relevant information"
}}

Partial summaries (JSON array):
{partials}
"""


@celery_app.task(bind=True, max_retries=2)
def summarize(self, diarize_result: dict) -> dict:
    """Generate structured meeting summary using LLM via LiteLLM."""
    meeting_id = diarize_result["meeting_id"]
    segments = diarize_result.get("segments", [])

    try:
        notify_meeting(meeting_id, "pipeline_progress", {"step": "summarize"})
        template = settings.SUMMARY_TEMPLATE or DEFAULT_SUMMARY_TEMPLATE

        summary_data = _summarize_transcript(segments, template)

        logger.info(f"Summary generated: {meeting_id}")

        out_segments = [] if diarize_result.get("summary_only") else segments
        return {
            "meeting_id": meeting_id,
            "summary": summary_data,
            "segments": out_segments,
            "summary_only": bool(diarize_result.get("summary_only")),
            "language": diarize_result.get("language"),
            "word_count": diarize_result.get("word_count", 0),
            "duration": diarize_result.get("duration"),
        }

    except Exception as exc:
        logger.error(f"Summarization failed for {meeting_id}: {exc}")
        summary_data = _build_fallback_summary(segments)
        return {
            "meeting_id": meeting_id,
            "summary": summary_data,
            "segments": [] if diarize_result.get("summary_only") else segments,
            "summary_only": bool(diarize_result.get("summary_only")),
            "language": diarize_result.get("language"),
            "word_count": diarize_result.get("word_count", 0),
            "duration": diarize_result.get("duration"),
            "summary_error": str(exc),
        }


def _summarize_transcript(segments: list[dict], template: str) -> dict[str, Any]:
    """Summarize full transcript; map-reduce when longer than threshold."""
    transcript_text = _format_transcript(segments)
    threshold = max(2000, int(settings.SUMMARY_MAP_REDUCE_THRESHOLD))
    chunk_size = max(4000, int(settings.SUMMARY_MAX_CHUNK_CHARS))

    if len(transcript_text) <= threshold:
        prompt = template.replace("{transcript}", transcript_text)
        summary_data = _call_llm(prompt)
        if not summary_data:
            summary_data = _call_llm_fallback(prompt)
        if not summary_data:
            summary_data = _build_fallback_summary(segments)
        return summary_data

    logger.info(
        f"Transcript {len(transcript_text)} chars > {threshold}, using map-reduce summarization"
    )
    return _summarize_map_reduce(segments, chunk_size)


def _summarize_map_reduce(segments: list[dict], chunk_size: int) -> dict[str, Any]:
    chunks = _chunk_segments(segments, chunk_size)
    partials: list[dict[str, Any]] = []

    for i, chunk_text in enumerate(chunks, start=1):
        prompt = MAP_CHUNK_TEMPLATE.format(
            part=i, total=len(chunks), transcript=chunk_text
        )
        part = _call_llm(prompt)
        if not part:
            part = _call_llm_fallback(prompt)
        if part:
            partials.append(part)
            logger.info(f"Map summary part {i}/{len(chunks)}: {len(part.get('key_points', []))} key_points")
        else:
            logger.warning(f"Map summary part {i}/{len(chunks)} returned empty")

    if not partials:
        return _build_fallback_summary(segments)

    if len(partials) == 1:
        return _normalize_summary(partials[0])

    merged = _reduce_summaries_llm(partials)
    if merged:
        return _normalize_summary(merged)

    logger.warning("Reduce step failed, merging partial summaries heuristically")
    return _merge_summaries_heuristic(partials)


def _reduce_summaries_llm(partials: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = REDUCE_TEMPLATE.format(
        count=len(partials),
        partials=json.dumps(partials, ensure_ascii=False, indent=2),
    )
    merged = _call_llm(prompt)
    if not merged:
        merged = _call_llm_fallback(prompt)
    return merged or {}


def _merge_summaries_heuristic(partials: list[dict[str, Any]]) -> dict[str, Any]:
    """Fallback merge when reduce LLM call fails."""
    title = ""
    date = None
    attendees: dict[str, dict] = {}
    key_points: list[dict] = []
    decisions: list[dict] = []
    action_items: list[dict] = []
    next_agendas: list[str] = []
    notes: list[str] = []

    for p in partials:
        if not title and p.get("title"):
            title = str(p["title"])
        if p.get("date") and not date:
            date = p.get("date")
        for a in p.get("attendees") or []:
            name = (a.get("name") or "").strip()
            if name and name not in attendees:
                attendees[name] = {"name": name, "is_guest": bool(a.get("is_guest", False))}
        key_points.extend(p.get("key_points") or [])
        decisions.extend(p.get("decisions") or [])
        action_items.extend(p.get("action_items") or [])
        na = (p.get("next_agenda") or "").strip()
        if na:
            next_agendas.append(na)
        note = (p.get("additional_notes") or "").strip()
        if note:
            notes.append(note)

    return _normalize_summary(
        {
            "title": title or "Meeting Summary",
            "date": date,
            "attendees": list(attendees.values()),
            "key_points": key_points,
            "decisions": decisions,
            "action_items": action_items,
            "next_agenda": next_agendas[-1] if next_agendas else "",
            "additional_notes": " ".join(notes),
        }
    )


def _normalize_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure expected keys exist with sane defaults."""
    return {
        "title": data.get("title") or "",
        "date": data.get("date"),
        "attendees": data.get("attendees") or [],
        "key_points": data.get("key_points") or [],
        "decisions": data.get("decisions") or [],
        "action_items": data.get("action_items") or [],
        "next_agenda": data.get("next_agenda") or "",
        "additional_notes": data.get("additional_notes") or "",
    }


def _chunk_segments(segments: list[dict], max_chars: int) -> list[str]:
    """Split transcript into chunks at segment boundaries."""
    chunks: list[str] = []
    lines: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal lines, size
        if lines:
            chunks.append("\n".join(lines))
        lines = []
        size = 0

    for seg in segments:
        line = (
            f"[{_format_time(seg.get('start', 0))}] "
            f"{seg.get('speaker_id') or 'Unknown'}: {seg.get('text', '')}"
        )
        line_len = len(line) + 1
        if size + line_len > max_chars and lines:
            flush()
        lines.append(line)
        size += line_len

    flush()
    return chunks or [""]


def _call_llm(prompt: str) -> dict[str, Any]:
    """Call LLM via LiteLLM proxy, with direct OpenAI/Ollama fallback."""
    proxy_url = getattr(settings, "LLM_PROXY_URL", "") or ""

    if proxy_url:
        return _call_via_litellm_proxy(prompt, proxy_url)
    return _call_direct(prompt)


def _call_via_litellm_proxy(prompt: str, proxy_url: str) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.LLM_API_KEY or "litellm-proxy",
        base_url=proxy_url.rstrip("/") + "/v1",
    )

    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": "You are a meeting summary assistant. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    return json.loads(_extract_json(content or ""))


def _call_direct(prompt: str) -> dict[str, Any]:
    from openai import DefaultHttpxClient, OpenAI
    import httpx

    api_key = settings.LLM_API_KEY or "ollama"
    base_url = settings.LLM_BASE_URL

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=DefaultHttpxClient(
            timeout=httpx.Timeout(1200.0, connect=30.0),
        ),
    )

    kwargs: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a meeting summary assistant. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "extra_body": {
            "num_ctx": 32768,
        },
    }

    try:
        kwargs["response_format"] = {"type": "json_object"}
    except Exception:
        pass

    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content
    return json.loads(_extract_json(content or ""))


def _format_transcript(segments: list[dict]) -> str:
    """Format transcript segments into readable text with speaker labels."""
    lines = []
    for seg in segments:
        speaker = seg.get("speaker_id") or "Unknown"
        text = seg.get("text", "")
        start = seg.get("start", 0)
        lines.append(f"[{_format_time(start)}] {speaker}: {text}")
    return "\n".join(lines)


def _format_time(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def _extract_json(text: str) -> str:
    """Extract JSON object from text that may contain markdown code blocks."""
    json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if json_match:
        return json_match.group(1)
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)
    return text


def _call_llm_fallback(prompt: str) -> dict[str, Any]:
    """Call LLM without response_format parameter (for models that don't support it)."""
    from openai import DefaultHttpxClient, OpenAI
    import httpx

    api_key = settings.LLM_API_KEY or "ollama"
    base_url = settings.LLM_BASE_URL

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=DefaultHttpxClient(
            timeout=httpx.Timeout(1200.0, connect=30.0),
        ),
    )

    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": "You are a meeting summary assistant. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        extra_body={
            "num_ctx": 32768,
        },
    )
    content = response.choices[0].message.content
    try:
        parsed = json.loads(_extract_json(content or ""))
        if parsed:
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def _build_fallback_summary(segments: list[dict]) -> dict[str, Any]:
    """Build a basic summary from transcript segments when LLM is unavailable."""
    unique_speakers = set()
    full_text: list[str] = []
    for seg in segments:
        speaker = seg.get("speaker_id") or "Unknown"
        unique_speakers.add(speaker)
        t = seg.get("text", "")
        if t:
            full_text.append(t)

    transcript_text = "".join(full_text)
    char_count = len(transcript_text.replace(" ", ""))
    description = transcript_text[:800] if transcript_text else ""

    return {
        "title": "",
        "date": None,
        "attendees": [{"name": s, "is_guest": False} for s in sorted(unique_speakers) if s != "Unknown"],
        "key_points": [{"topic": "Discussion", "description": description, "importance": 3}],
        "decisions": [],
        "action_items": [],
        "next_agenda": "",
        "additional_notes": f"Auto-generated summary ({char_count} chars, {len(unique_speakers)} speakers)",
    }
