from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.tasks.transcriber.base import BaseTranscriber, TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)


class FasterWhisperProvider(BaseTranscriber):
    """Transcription provider using faster-whisper (CTranslate2 backend).

    Downloads models from ModelScope by default, falls back to HuggingFace.
    Supports all whisper model sizes: tiny, base, small, medium, large-v3.
    """

    # ModelScope → faster-whisper model name mapping
    WHISPER_MODELSCOPE_MAP = {
        "tiny": "modelscope/Systran/faster-whisper-tiny",
        "base": "modelscope/Systran/faster-whisper-base",
        "small": "modelscope/Systran/faster-whisper-small",
        "medium": "modelscope/Systran/faster-whisper-medium",
        "large-v2": "modelscope/Systran/faster-whisper-large-v2",
        "large-v3": "modelscope/Systran/faster-whisper-large-v3",
    }

    def __init__(self):
        self._model = None

    def get_model_name(self) -> str:
        return f"faster-whisper/{settings.WHISPER_MODEL}"

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Transcribe audio using faster-whisper with VAD filtering."""
        from faster_whisper import WhisperModel

        model = self._get_model()

        segments_gen, info = model.transcribe(
            audio_path,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        segments: list[TranscriptionSegment] = []
        word_count = 0

        for seg in segments_gen:
            segments.append(TranscriptionSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                confidence=getattr(seg, "avg_logprob", None),
            ))
            word_count += len(seg.text.split()) if seg.text else 0

        logger.info(
            f"FasterWhisper: {word_count} words, lang={info.language}, "
            f"segments={len(segments)}"
        )

        return TranscriptionResult(
            segments=segments,
            language=info.language,
            word_count=word_count,
        )

    def _get_model(self):
        """Lazy-loaded singleton for the WhisperModel instance."""
        if self._model is None:
            from faster_whisper import WhisperModel

            model_size = settings.WHISPER_MODEL
            model_path = self._ensure_model(model_size)

            logger.info(
                f"Loading Whisper model: {model_size} "
                f"from {model_path} on {settings.WHISPER_DEVICE}"
            )
            self._model = WhisperModel(
                model_path,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
                download_root=None,
            )
            logger.info("Whisper model loaded")
        return self._model

    def _ensure_model(self, model_size: str) -> str:
        """Download whisper model from ModelScope if not cached, return local path."""
        cache_dir = Path(settings.STORAGE_PATH) / "models" / "whisper" / model_size

        if cache_dir.exists() and (cache_dir / "model.bin").exists():
            logger.info(f"Whisper model cached at {cache_dir}")
            return str(cache_dir)

        modelscope_repo = self.WHISPER_MODELSCOPE_MAP.get(model_size)
        if modelscope_repo:
            try:
                logger.info(f"Downloading whisper model from ModelScope: {modelscope_repo}")
                self._download_from_modelscope(modelscope_repo, cache_dir)
                if (cache_dir / "model.bin").exists():
                    return str(cache_dir)
            except Exception as e:
                logger.warning(f"ModelScope download failed: {e}, falling back to HuggingFace")

        logger.info("Using HuggingFace fallback for whisper model")
        return model_size

    @staticmethod
    def _download_from_modelscope(repo_id: str, target_dir: Path) -> None:
        """Download model files from ModelScope hub."""
        from modelscope.hub.snapshot_download import snapshot_download

        target_dir.mkdir(parents=True, exist_ok=True)
        actual_repo = repo_id.replace("modelscope/", "", 1)

        snapshot_download(
            actual_repo,
            cache_dir=str(target_dir.parent),
            local_dir=str(target_dir),
        )
        logger.info(f"Downloaded {repo_id} to {target_dir}")
