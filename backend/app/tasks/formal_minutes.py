"""Generate formal Chinese meeting minutes (集团会议纪要) from transcript."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from app.config import settings
from app.models.meeting import Meeting

logger = logging.getLogger(__name__)

FORMAL_MINUTES_SYSTEM = (
    "你是大型集团会议纪要撰写专家。根据会议录音转写稿撰写正式「纪要」公文。"
    "要求：语言庄重、准确、书面化；将口语整理为纪要表述；分条用「一、」「二、」等中文序号；"
    "不要编造转写中未出现的事实；出席名单仅列转写或摘要中明确出现的人员。"
    "只输出纪要正文，不要 Markdown 代码块，不要 JSON。"
)

SINGLE_MINUTES_TEMPLATE = """请根据以下信息撰写完整会议纪要。

{meta_block}

【结构化摘要参考（辅助提炼，勿逐条照搬）】
{summary_hint}

【会议转写稿】
{transcript}

输出格式要求：
1. 首行居中标题写「纪要」（不要加书名号）。
2. 接着会议主题、会议时间、会议地点、会议主持、会议记录、纪要审核与签发人（审核、签发留空栏即可）。
3. 一段综述（说明何时、谁召集、什么会议、总体议题与共识，2–4 句）。
4. 正文分条「一、」「二、」…，每条先写小标题式短语，再写 1–3 段正式叙述。
5. 末行「出席：」后列参会人员（姓名用顿号分隔）。
6. 倒数第二行写记录单位；最后一行写纪要日期（YYYY年M月D日）。

若某项信息未知，写「待补充」，不要虚构地点或单位。"""

MAP_MINUTES_TEMPLATE = """以下是长会议转写稿的第 {part}/{total} 部分。请提炼本部分应写入正式纪要的内容。
输出 JSON：
{{
  "section_drafts": [
    {{"heading": "一、简短小标题", "paragraphs": ["正式段落1", "正式段落2"]}}
  ]
}}
若无实质内容则 "section_drafts": []。

{meta_block}

转写片段：
{transcript}
"""

REDUCE_MINUTES_TEMPLATE = """请将多段会议纪要草稿合并为一份完整、连贯的正式会议纪要。
合并时去重、理顺序号（一、二、三…）、统一表述风格。

{meta_block}

草稿 JSON 列表：
{drafts}

按下列格式输出完整纪要正文（纯文本）：
纪要标题行、会议要素行、综述段、分条正文、出席、记录单位、日期。"""


def generate_formal_minutes(
    meeting: Meeting,
    segments: list[dict],
    structured_summary: dict[str, Any],
) -> str:
    """Build formal minutes text; uses map-reduce on long transcripts."""
    transcript_text = _format_transcript(segments)
    meta_block = _build_meta_block(meeting, structured_summary)
    summary_hint = _format_summary_hint(structured_summary)
    threshold = max(2000, int(settings.SUMMARY_MAP_REDUCE_THRESHOLD))

    if len(transcript_text) <= threshold:
        prompt = SINGLE_MINUTES_TEMPLATE.format(
            meta_block=meta_block,
            summary_hint=summary_hint,
            transcript=transcript_text,
        )
        text = _call_llm_text(prompt)
        if text:
            return _normalize_minutes_text(text)

    # Long meeting: prefer single-pass from structured summary + transcript excerpt
    if structured_summary.get("key_points"):
        excerpt = transcript_text[:threshold]
        if len(transcript_text) > threshold:
            excerpt += "\n\n…（转写稿中段已省略，详见结构化摘要）…\n\n"
            excerpt += transcript_text[-min(4000, threshold // 2) :]
        logger.info(
            "Formal minutes: using summary-assisted single pass (%s chars excerpt)",
            len(excerpt),
        )
        prompt = SINGLE_MINUTES_TEMPLATE.format(
            meta_block=meta_block,
            summary_hint=summary_hint,
            transcript=excerpt,
        )
        text = _call_llm_text(prompt)
        if text:
            return _normalize_minutes_text(text)

    logger.info(
        "Formal minutes: transcript %s chars > %s, map-reduce",
        len(transcript_text),
        threshold,
    )
    return _generate_formal_minutes_map_reduce(
        meeting, segments, meta_block, summary_hint, threshold
    )


def _generate_formal_minutes_map_reduce(
    meeting: Meeting,
    segments: list[dict],
    meta_block: str,
    summary_hint: str,
    chunk_size: int,
) -> str:
    from app.tasks.summarize import _chunk_segments

    chunks = _chunk_segments(segments, chunk_size)
    all_drafts: list[dict] = []

    for i, chunk_text in enumerate(chunks, start=1):
        prompt = MAP_MINUTES_TEMPLATE.format(
            part=i,
            total=len(chunks),
            meta_block=meta_block,
            transcript=chunk_text,
        )
        part = _call_llm_json(prompt)
        if part and part.get("section_drafts"):
            all_drafts.extend(part["section_drafts"])

    if not all_drafts:
        prompt = SINGLE_MINUTES_TEMPLATE.format(
            meta_block=meta_block,
            summary_hint=summary_hint,
            transcript=_format_transcript(segments)[:chunk_size * 2],
        )
        text = _call_llm_text(prompt)
        return _normalize_minutes_text(text) if text else ""

    reduce_prompt = REDUCE_MINUTES_TEMPLATE.format(
        meta_block=meta_block,
        drafts=json.dumps(all_drafts, ensure_ascii=False, indent=2),
    )
    text = _call_llm_text(reduce_prompt)
    return _normalize_minutes_text(text) if text else _fallback_minutes(meeting, all_drafts)


def _build_meta_block(meeting: Meeting, summary: dict[str, Any]) -> str:
    host = (meeting.host or settings.DEFAULT_MEETING_HOST or "董事长").strip()
    recorder = (meeting.recorder_unit or "").strip() or "待补充"
    location = (meeting.meeting_location or "").strip() or "待补充"
    theme = (meeting.title or summary.get("title") or "待补充").strip()
    when = _format_meeting_datetime(meeting, summary)
    attendees = _attendee_names(summary)

    lines = [
        f"会议主题：{theme}",
        f"会议时间：{when}",
        f"会议地点：{location}",
        f"会议主持：{host}",
        f"会议记录：{recorder}",
        f"已知参会人员参考：{attendees}",
    ]
    return "\n".join(lines)


def _format_meeting_datetime(meeting: Meeting, summary: dict[str, Any]) -> str:
    dt = meeting.date
    if not dt and summary.get("date"):
        try:
            raw = summary["date"]
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
    if dt:
        if meeting.duration_seconds:
            end = dt
            # naive: show start date only if no end time in data
            return f"{dt.year}年{dt.month}月{dt.day}日"
        return f"{dt.year}年{dt.month}月{dt.day}日"
    return "待补充"


def _attendee_names(summary: dict[str, Any]) -> str:
    names = []
    for a in summary.get("attendees") or []:
        n = (a.get("name") or "").strip()
        if n and not n.startswith("SPEAKER_"):
            names.append(n)
    return "、".join(names) if names else "见转写稿"


def _format_summary_hint(summary: dict[str, Any]) -> str:
    parts = []
    if summary.get("key_points"):
        parts.append("要点：" + "; ".join(
            (kp.get("topic") or "") + (kp.get("description") or "")[:200]
            for kp in summary["key_points"][:12]
        ))
    if summary.get("decisions"):
        parts.append("决策：" + "; ".join(
            (d.get("description") or "")[:200] for d in summary["decisions"][:8]
        ))
    if summary.get("action_items"):
        parts.append("待办：" + "; ".join(
            (ai.get("description") or "")[:120] for ai in summary["action_items"][:8]
        ))
    return "\n".join(parts) if parts else "（无）"


def _format_transcript(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        speaker = seg.get("speaker_id") or "未知"
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = seg.get("start", 0)
        lines.append(f"[{_format_time(start)}] {speaker}: {text}")
    return "\n".join(lines)


def _format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _normalize_minutes_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:markdown|text)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


def _fallback_minutes(meeting: Meeting, drafts: list[dict]) -> str:
    """Assemble minutes from section drafts when reduce LLM fails."""
    lines = ["纪要", "", _build_meta_block(meeting, {}), ""]
    for d in drafts:
        h = d.get("heading") or ""
        if h:
            lines.append(h)
        for p in d.get("paragraphs") or []:
            if p:
                lines.append(str(p))
        lines.append("")
    lines.append(f"{meeting.recorder_unit or '待补充'}")
    if meeting.date:
        lines.append(f"{meeting.date.year}年{meeting.date.month}月{meeting.date.day}日")
    return "\n".join(lines)


def _call_llm_text(prompt: str) -> str:
    from openai import DefaultHttpxClient, OpenAI
    import httpx

    proxy_url = (settings.LLM_PROXY_URL or "").strip()
    if proxy_url:
        client = OpenAI(
            api_key=settings.LLM_API_KEY or "litellm-proxy",
            base_url=proxy_url.rstrip("/") + "/v1",
        )
    else:
        client = OpenAI(
            api_key=settings.LLM_API_KEY or "ollama",
            base_url=settings.LLM_BASE_URL,
            http_client=DefaultHttpxClient(timeout=httpx.Timeout(1200.0, connect=30.0)),
        )

    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": FORMAL_MINUTES_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.25,
    )
    return (response.choices[0].message.content or "").strip()


def _call_llm_json(prompt: str) -> dict[str, Any]:
    from openai import DefaultHttpxClient, OpenAI
    import httpx

    proxy_url = (settings.LLM_PROXY_URL or "").strip()
    if proxy_url:
        client = OpenAI(
            api_key=settings.LLM_API_KEY or "litellm-proxy",
            base_url=proxy_url.rstrip("/") + "/v1",
        )
        kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}}
    else:
        client = OpenAI(
            api_key=settings.LLM_API_KEY or "ollama",
            base_url=settings.LLM_BASE_URL,
            http_client=DefaultHttpxClient(timeout=httpx.Timeout(1200.0, connect=30.0)),
        )
        kwargs = {}
        try:
            kwargs["response_format"] = {"type": "json_object"}
        except Exception:
            pass

    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": "Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.25,
        **kwargs,
    )
    content = response.choices[0].message.content or ""
    from app.tasks.summarize import _extract_json

    try:
        return json.loads(_extract_json(content))
    except json.JSONDecodeError:
        return {}
