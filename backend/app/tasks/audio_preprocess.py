from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.tasks.celery_app import celery_app
from app.utils.audio import extract_audio, get_audio_duration, normalize_audio

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def audio_preprocess(self, meeting_id: str, audio_path: str) -> dict:
    """Preprocess audio: extract, normalize, convert to 16kHz mono WAV."""
    try:
        input_path = Path(audio_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Create preprocessed filename
        preprocessed_dir = Path(settings.STORAGE_PATH) / "preprocessed"
        preprocessed_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(preprocessed_dir / f"{meeting_id}.wav")

        # Extract audio (handles video files too)
        wav_path = extract_audio(audio_path, output_path)

        # Normalize loudness (use temp file to avoid in-place overwrite issues)
        norm_output = str(preprocessed_dir / f"{meeting_id}_normalized.wav")
        normalized_path = normalize_audio(audio_path, norm_output)

        # Get duration
        duration = get_audio_duration(normalized_path)

        logger.info(f"Audio preprocessed: {normalized_path}, duration: {duration}s")

        return {
            "meeting_id": meeting_id,
            "audio_path": str(normalized_path),
            "duration": duration,
        }

    except Exception as exc:
        logger.error(f"Audio preprocessing failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
