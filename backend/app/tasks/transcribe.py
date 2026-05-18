from __future__ import annotations

import logging

from app.tasks.celery_app import celery_app
from app.tasks.transcriber.base import TranscriptionResult
from app.tasks.transcriber.factory import get_transcriber

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def transcribe(self, preprocess_result: dict) -> dict:
    """Transcribe audio using the configured ASR provider."""
    meeting_id = preprocess_result["meeting_id"]
    audio_path = preprocess_result["audio_path"]

    try:
        transcriber = get_transcriber()
        result: TranscriptionResult = transcriber.transcribe(audio_path)

        logger.info(
            f"Transcription complete: {meeting_id}, "
            f"{result.word_count} words, lang={result.language}, "
            f"provider={transcriber.get_model_name()}"
        )

        return {
            "meeting_id": meeting_id,
            "audio_path": audio_path,
            "language": result.language,
            "model_used": transcriber.get_model_name(),
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "confidence": s.confidence,
                }
                for s in result.segments
            ],
            "word_count": result.word_count,
        }

    except Exception as exc:
        logger.error(f"Transcription failed for {meeting_id}: {exc}")
        raise self.retry(exc=exc, countdown=30)
