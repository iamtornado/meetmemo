from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranscriptionSegment:
    """Unified segment format that all providers must return.

    Attributes:
        start: Start time in seconds.
        end: End time in seconds.
        text: Transcribed text.
        confidence: Confidence score (provider-specific, may be None).
    """
    start: float
    end: float
    text: str
    confidence: Optional[float] = None


@dataclass
class TranscriptionResult:
    """Unified result format returned by all providers."""
    segments: list[TranscriptionSegment] = field(default_factory=list)
    language: str = "unknown"
    word_count: int = 0


class BaseTranscriber(abc.ABC):
    """Abstract base class for transcription providers."""

    @abc.abstractmethod
    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Transcribe audio file and return structured result.

        Args:
            audio_path: Path to the preprocessed audio file (16kHz mono WAV).

        Returns:
            TranscriptionResult with segments, language, and word_count.
        """
        ...

    @abc.abstractmethod
    def get_model_name(self) -> str:
        """Return a human-readable identifier for the model used.

        This value is stored in the transcript record (model_used field).
        Example: 'faster-whisper/base', 'sensevoice/SenseVoiceSmall'
        """
        ...
