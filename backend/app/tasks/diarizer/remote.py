from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from app.config import settings
from app.tasks.diarizer.base import BaseDiarizer, DiarizationResult, DiarizationSegment

logger = logging.getLogger(__name__)


class RemoteDiarizer(BaseDiarizer):
    """Diarization provider that sends audio to a remote pyannote API server.

    Useful when pyannote is deployed on a remote GPU server for fast inference.
    Configure via DIARIZE_API_URL environment variable.

    Expected remote API:
        POST /diarize
            Request:  multipart/form-data with audio file
            Response: {
                "speaker_segments": [
                    {"speaker": "SPEAKER_00", "start": 0.0, "end": 2.5},
                    ...
                ],
                "num_speakers": 2
            }

        GET /health -> {"status": "ok"}
    """

    def __init__(self):
        self._api_url = settings.DIARIZE_API_URL.rstrip("/")

    def get_model_name(self) -> str:
        return f"pyannote/remote"

    def diarize(self, audio_path: str) -> DiarizationResult:
        """Send audio file to remote pyannote API for diarization."""
        logger.info(f"RemoteDiarizer: sending {audio_path} to {self._api_url}")

        audio_path_obj = Path(audio_path)
        if not audio_path_obj.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        with open(audio_path, "rb") as f:
            files = {"audio": (audio_path_obj.name, f, "audio/wav")}
            try:
                response = httpx.post(
                    f"{self._api_url}/diarize",
                    files=files,
                    timeout=httpx.Timeout(1800.0, connect=30.0),
                )
                response.raise_for_status()
            except httpx.TimeoutException:
                logger.error(f"Remote diarization timed out for {audio_path}")
                raise
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Remote diarization failed with status {e.response.status_code}: "
                    f"{e.response.text}"
                )
                raise

            data = response.json()

        return self._parse_response(data)

    @staticmethod
    def _parse_response(data: dict) -> DiarizationResult:
        """Parse remote API response into DiarizationResult.

        Expected format:
        {
            "speaker_segments": [
                {"speaker": "SPEAKER_00", "start": 0.0, "end": 2.5},
                ...
            ],
            "num_speakers": 2
        }
        """
        segments_raw = data.get("speaker_segments", [])
        speaker_segments = [
            DiarizationSegment(
                speaker=s["speaker"],
                start=float(s["start"]),
                end=float(s["end"]),
            )
            for s in segments_raw
            if s.get("start") is not None and s.get("end") is not None
        ]

        num_speakers = data.get("num_speakers", len(set(s.speaker for s in speaker_segments)))

        logger.info(
            f"Remote diarization result: {len(speaker_segments)} segments, "
            f"{num_speakers} speakers"
        )

        return DiarizationResult(
            speaker_segments=speaker_segments,
            num_speakers=num_speakers,
        )
