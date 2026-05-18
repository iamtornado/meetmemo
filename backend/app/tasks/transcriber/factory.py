from __future__ import annotations

import logging
from typing import Literal

from app.config import settings
from app.tasks.transcriber.base import BaseTranscriber

logger = logging.getLogger(__name__)

TranscribeProvider = Literal["faster-whisper", "sensevoice"]

# Module-level singleton cache
_transcriber_instance: BaseTranscriber | None = None


def get_transcriber() -> BaseTranscriber:
    """Factory function — returns a singleton transcriber based on ASR_PROVIDER.

    The provider is resolved at first call (lazy) and cached for the lifetime
    of the worker process.
    """
    global _transcriber_instance

    if _transcriber_instance is not None:
        return _transcriber_instance

    provider: TranscribeProvider = settings.ASR_PROVIDER

    logger.info(f"Initializing transcriber provider: {provider}")

    if provider == "faster-whisper":
        from app.tasks.transcriber.faster_whisper import FasterWhisperProvider
        _transcriber_instance = FasterWhisperProvider()
    elif provider == "sensevoice":
        if settings.SENSEVOICE_MODE == "remote":
            from app.tasks.transcriber.sensevoice import SenseVoiceRemoteProvider
            _transcriber_instance = SenseVoiceRemoteProvider()
        else:
            from app.tasks.transcriber.sensevoice import SenseVoiceProvider
            _transcriber_instance = SenseVoiceProvider()
    else:
        raise ValueError(
            f"Unknown ASR_PROVIDER: {provider!r}. "
            f"Expected one of: {get_available_providers()}"
        )

    logger.info(f"Transcriber provider initialized: {type(_transcriber_instance).__name__}")
    return _transcriber_instance


def get_available_providers() -> list[TranscribeProvider]:
    return ["faster-whisper", "sensevoice"]


def reset_transcriber() -> None:
    """Reset the cached transcriber instance (useful for tests / config reload)."""
    global _transcriber_instance
    _transcriber_instance = None
    logger.debug("Transcriber instance reset")
