from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_audio(input_path: str, output_path: str, sample_rate: int = 16000) -> str:
    """Extract and convert audio to 16kHz mono WAV using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vn",  # No video
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",  # Mono
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg error: {result.stderr}")
        raise RuntimeError(f"Audio extraction failed: {result.stderr}")
    return output_path


def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"FFprobe error: {result.stderr}")
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def normalize_audio(input_path: str, output_path: str) -> str:
    """Normalize audio loudness using ffmpeg loudnorm filter."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
        "-ar", "16000",
        "-ac", "1",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"Audio normalization failed, using original: {result.stderr}")
        return input_path
    return output_path
