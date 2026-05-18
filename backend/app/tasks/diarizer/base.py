from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiarizationSegment:
    """A single speaker segment from diarization.

    Attributes:
        speaker: Speaker label (e.g. "SPEAKER_00", "SPEAKER_01").
        start: Start time in seconds.
        end: End time in seconds.
    """
    speaker: str
    start: float
    end: float


@dataclass
class DiarizationResult:
    """Unified result format returned by all diarization providers."""
    speaker_segments: list[DiarizationSegment] = field(default_factory=list)
    num_speakers: int = 0


class BaseDiarizer(abc.ABC):
    """Abstract base class for diarization providers."""

    @abc.abstractmethod
    def diarize(self, audio_path: str) -> DiarizationResult:
        """Run speaker diarization on audio file.

        Args:
            audio_path: Path to the preprocessed audio file (16 kHz mono WAV).

        Returns:
            DiarizationResult with speaker segments and speaker count.
        """
        ...

    @abc.abstractmethod
    def get_model_name(self) -> str:
        """Return a human-readable identifier for the diarization model used.

        Example: 'pyannote/speaker-diarization-3.1', 'pyannote/remote'
        """
        ...
