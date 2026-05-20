from __future__ import annotations

import logging

from app.tasks.celery_app import celery_app
from app.tasks.diarizer.base import DiarizationResult
from app.tasks.diarizer.factory import get_diarizer
from app.tasks.pipeline_helpers import notify_meeting
from app.utils.speaker_merge import merge_diarization_with_transcript

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
        notify_meeting(meeting_id, "pipeline_progress", {"step": "diarize"})
        diarizer = get_diarizer()
        result: DiarizationResult = diarizer.diarize(audio_path)

        # Merge diarization with transcript segments
        merged = merge_diarization_with_transcript(segments, result.speaker_segments)

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


