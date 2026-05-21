"""Merge fine-grained ASR segments (char/word level) into sentence-level timeline."""

from __future__ import annotations

import re
from typing import Any

# Sentence-ending punctuation (Chinese + Western)
_SENTENCE_END_RE = re.compile(r"[。！？!?；;…][\"'”』】）)]*$")

# Gap longer than this starts a new sentence block
_MAX_GAP_SEC = 0.9

# Align with SenseVoice merge_length_s default
_MAX_SEGMENT_DURATION_SEC = 15.0

# Force flush when buffer grows too large without punctuation
_MAX_SEGMENT_CHARS = 100


def _append_fragment(buffer: str, piece: str) -> str:
    if not piece:
        return buffer
    if not buffer:
        return piece
    # Insert space between consecutive Latin tokens
    if (
        buffer[-1].isalnum()
        and piece[0].isalnum()
        and ord(buffer[-1]) < 128
        and ord(piece[0]) < 128
    ):
        return f"{buffer} {piece}"
    return buffer + piece


def needs_sentence_merge(segments: list[dict[str, Any]]) -> bool:
    """True when segments look like CTC char/word level rather than sentences."""
    if len(segments) < 25:
        return False
    lengths = [len(str(s.get("text", "")).strip()) for s in segments if s.get("text")]
    if not lengths:
        return False
    return sum(lengths) / len(lengths) < 3.0


def merge_to_sentence_level(
    segments: list[dict[str, Any]],
    *,
    max_duration_sec: float = _MAX_SEGMENT_DURATION_SEC,
    max_gap_sec: float = _MAX_GAP_SEC,
    max_chars: int = _MAX_SEGMENT_CHARS,
) -> list[dict[str, Any]]:
    """Merge micro-segments into sentence-level blocks with start/end times."""
    if not segments:
        return []

    ordered = sorted(segments, key=lambda s: float(s.get("start", 0)))
    merged: list[dict[str, Any]] = []

    buf_text = ""
    buf_start: float | None = None
    buf_end: float | None = None

    def flush() -> None:
        nonlocal buf_text, buf_start, buf_end
        text = buf_text.strip()
        if text and buf_start is not None:
            merged.append(
                {
                    "start": buf_start,
                    "end": buf_end if buf_end is not None else buf_start + 0.5,
                    "text": text,
                }
            )
        buf_text = ""
        buf_start = None
        buf_end = None

    for seg in ordered:
        piece = str(seg.get("text", "")).strip()
        if not piece:
            continue

        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        if end < start:
            end = start

        if buf_start is None:
            buf_start = start
        elif start - (buf_end or start) > max_gap_sec:
            flush()
            buf_start = start

        buf_text = _append_fragment(buf_text, piece)
        buf_end = max(buf_end or end, end)

        duration = (buf_end or start) - (buf_start or start)
        if (
            _SENTENCE_END_RE.search(buf_text)
            or duration >= max_duration_sec
            or len(buf_text) >= max_chars
        ):
            flush()

    flush()
    return merged
