from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.tasks.celery_app import celery_app

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


@celery_app.task(bind=True, max_retries=2)
def summarize(self, diarize_result: dict) -> dict:
    """Generate structured meeting summary using LLM via LiteLLM."""
    meeting_id = diarize_result["meeting_id"]
    segments = diarize_result.get("segments", [])

    try:
        transcript_text = _format_transcript(segments)
        template = settings.SUMMARY_TEMPLATE or DEFAULT_SUMMARY_TEMPLATE

        # Truncate transcript to fit within context window (16k tokens ≈ ~20k chars for Chinese)
        # Reserve ~2k chars for template + output
        max_transcript_chars = 12000
        if len(transcript_text) > max_transcript_chars:
            logger.warning(
                f"Transcript too long ({len(transcript_text)} chars), "
                f"truncating to {max_transcript_chars}"
            )
            transcript_text = transcript_text[:max_transcript_chars] + "\n... [transcript truncated]"

        prompt = template.replace("{transcript}", transcript_text)

        summary_data = _call_llm(prompt)

        # If LLM returned empty dict, try without response_format
        if not summary_data or summary_data == {}:
            logger.warning("LLM returned empty summary, retrying without response_format")
            summary_data = _call_llm_fallback(prompt)

        # If still empty, build a minimal summary from the transcript
        if not summary_data or summary_data == {}:
            logger.warning("Using fallback summary from transcript")
            summary_data = _build_fallback_summary(segments)

        logger.info(f"Summary generated: {meeting_id}")

        # Pass through segments from diarize result for store_results
        return {
            "meeting_id": meeting_id,
            "summary": summary_data,
            "segments": segments,
            "language": diarize_result.get("language"),
            "word_count": diarize_result.get("word_count", 0),
            "duration": diarize_result.get("duration"),
        }

    except Exception as exc:
        logger.error(f"Summarization failed for {meeting_id}: {exc}")
        raise self.retry(exc=exc, countdown=30)


def _call_llm(prompt: str) -> dict[str, Any]:
    """Call LLM via LiteLLM proxy, with direct OpenAI/Ollama fallback."""
    # Priority: LiteLLM proxy URL > direct provider
    proxy_url = getattr(settings, "LLM_PROXY_URL", "") or ""

    if proxy_url:
        return _call_via_litellm_proxy(prompt, proxy_url)
    else:
        return _call_direct(prompt)


def _call_via_litellm_proxy(prompt: str, proxy_url: str) -> dict[str, Any]:
    """Call LLM through a LiteLLM proxy server.

    LiteLLM proxy exposes a single OpenAI-compatible endpoint that
    routes to any provider (OpenAI, Claude, Gemini, Azure, Ollama, etc.).

    Environment setup:
        LLM_PROXY_URL=http://litellm:4000
        LLM_API_KEY=sk-litellm-proxy-key
        LLM_MODEL=openai/gpt-4o  (or claude-sonnet-4-20250514, gemini/gemini-2.0-flash, etc.)
    """
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
    """Call LLM directly (Ollama or OpenAI-compatible endpoint)."""
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

    # response_format is not supported by all providers (Ollama older versions)
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
    from openai import OpenAI

    api_key = settings.LLM_API_KEY or "ollama"
    base_url = settings.LLM_BASE_URL

    from openai import DefaultHttpxClient
    import httpx

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
        if parsed:  # Only return non-empty dicts
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def _build_fallback_summary(segments: list[dict]) -> dict[str, Any]:
    """Build a basic summary from transcript segments when LLM is unavailable."""
    unique_speakers = set()
    full_text = []
    for seg in segments:
        speaker = seg.get("speaker_id") or "Unknown"
        unique_speakers.add(speaker)
        full_text.append(seg.get("text", ""))

    transcript_text = " ".join(full_text)
    words = transcript_text.split()
    # Take first 200 words as description
    description = " ".join(words[:200]) if words else ""

    return {
        "title": "",
        "date": None,
        "attendees": [{"name": s, "is_guest": False} for s in sorted(unique_speakers) if s != "Unknown"],
        "key_points": [{"topic": "Discussion", "description": description, "importance": 3}],
        "decisions": [],
        "action_items": [],
        "next_agenda": "",
        "additional_notes": f"Auto-generated summary ({len(words)} words, {len(unique_speakers)} speakers)",
    }
