from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def _normalize_speaker_segment(sp: Any) -> tuple[float, float, str]:
    if isinstance(sp, dict):
        return float(sp["start"]), float(sp["end"]), str(sp["speaker"])
    return float(sp.start), float(sp.end), str(sp.speaker)


def merge_diarization_with_transcript(
    segments: list[dict],
    speaker_segments: list[Any],
) -> list[dict]:
    """Assign speaker_id to each transcript segment by total time overlap.

    Uses per-speaker accumulated overlap (majority within the sentence window),
    not a single best pyannote slice. Works with sentence-level ASR segments.
    """
    if not speaker_segments:
        return [{**s, "speaker_id": None} for s in segments]

    normalized = [_normalize_speaker_segment(sp) for sp in speaker_segments]
    min_sec = settings.DIARIZE_MERGE_MIN_OVERLAP_SEC
    min_ratio = settings.DIARIZE_MERGE_MIN_OVERLAP_RATIO

    merged: list[dict] = []
    for seg in segments:
        seg_start = float(seg["start"])
        seg_end = float(seg["end"])
        seg_duration = max(seg_end - seg_start, 0.0)

        overlap_by_speaker: dict[str, float] = {}

        for sp_start, sp_end, sp_speaker in normalized:
            overlap_start = max(seg_start, sp_start)
            overlap_end = min(seg_end, sp_end)
            overlap = max(0.0, overlap_end - overlap_start)
            if overlap > 0:
                overlap_by_speaker[sp_speaker] = (
                    overlap_by_speaker.get(sp_speaker, 0.0) + overlap
                )

        # Zero-duration segment: pick who is active at the timestamp
        if seg_duration < 0.01:
            for sp_start, sp_end, sp_speaker in normalized:
                if sp_start <= seg_start < sp_end:
                    overlap_by_speaker[sp_speaker] = (
                        overlap_by_speaker.get(sp_speaker, 0.0) + 1.0
                    )

        best_speaker: str | None = None
        best_overlap = 0.0
        for speaker, total in overlap_by_speaker.items():
            if total > best_overlap:
                best_overlap = total
                best_speaker = speaker

        if seg_duration > 0:
            threshold = max(min_sec, seg_duration * min_ratio)
        else:
            threshold = min_sec

        if best_overlap < threshold:
            best_speaker = None

        merged.append({**seg, "speaker_id": best_speaker})

    assigned = {m["speaker_id"] for m in merged if m.get("speaker_id")}
    logger.info(
        f"Speaker merge: {len(assigned)} distinct speakers on "
        f"{len(merged)} transcript segments"
    )
    return merged
