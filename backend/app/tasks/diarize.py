from __future__ import annotations

import logging

from app.tasks.celery_app import celery_app
from app.tasks.diarizer.base import DiarizationResult
from app.tasks.diarizer.factory import get_diarizer

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def diarize(self, transcribe_result: dict) -> dict:
    """Perform speaker diarization using the configured diarizer provider.

    Delegates to the provider selected by DIARIZE_PROVIDER:
      - "local"  → LocalDiarizer (pyannote.audio in-container, CPU)
      - "remote" → RemoteDiarizer (HTTP API to remote GPU server)

    If diarization fails entirely, speaker_id is set to None for all segments
    and the pipeline continues.
    """
    meeting_id = transcribe_result["meeting_id"]
    audio_path = transcribe_result["audio_path"]
    segments = transcribe_result.get("segments", [])

    try:
        diarizer = get_diarizer()
        result: DiarizationResult = diarizer.diarize(audio_path)

        # Merge diarization with transcript segments
        merged = _merge_diarization(segments, result.speaker_segments)

        logger.info(
            f"Diarization complete: {meeting_id}, "
            f"{len(result.speaker_segments)} speaker segments, "
            f"{result.num_speakers} speakers, "
            f"provider={diarizer.get_model_name()}"
        )

        return {
            "meeting_id": meeting_id,
            "segments": merged,
            "language": transcribe_result.get("language"),
            "model_used": diarizer.get_model_name(),
            "word_count": transcribe_result.get("word_count", 0),
            "duration": transcribe_result.get("duration"),
        }

    except Exception as exc:
        logger.error(f"Diarization failed for {meeting_id}: {exc}")
        # If diarization fails, return original segments without speaker labels
        return {
            "meeting_id": meeting_id,
            "segments": [
                {**s, "speaker_id": None} for s in segments
            ],
            "language": transcribe_result.get("language"),
            "model_used": transcribe_result.get("model_used"),
            "word_count": transcribe_result.get("word_count", 0),
            "duration": transcribe_result.get("duration"),
        }


def _merge_diarization(segments: list[dict], speaker_segments: list[dict]) -> list[dict]:
    """Merge diarization speaker labels into transcript segments by time overlap."""
    if not speaker_segments:
        return [{**s, "speaker_id": None} for s in segments]

    merged = []
    for seg in segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        seg_duration = seg_end - seg_start

        best_speaker = None
        best_overlap = 0

        for sp in speaker_segments:
            overlap_start = max(seg_start, sp["start"])
            overlap_end = min(seg_end, sp["end"])
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = sp["speaker"]

        # Only assign speaker if overlap is significant (>20%)
        if best_overlap < seg_duration * 0.2:
            best_speaker = None

        merged.append({**seg, "speaker_id": best_speaker})

    return merged
