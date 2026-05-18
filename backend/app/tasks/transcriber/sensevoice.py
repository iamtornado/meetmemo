from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings
from app.tasks.transcriber.base import BaseTranscriber, TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)


class SenseVoiceProvider(BaseTranscriber):
    """Transcription provider using SenseVoice (阿里通义) via funasr AutoModel.

    Local mode: runs iic/SenseVoiceSmall directly inside the container.
    Uses FSMN-VAD for voice activity detection and segmentation.

    Features:
    - Optimized for Chinese ASR (better than Whisper for Chinese)
    - Built-in emotion/event detection (stripped from output)
    - Built-in inverse text normalization (punctuation, numbers)
    - Auto language detection
    """

    def __init__(self):
        self._model = None
        self._vad_model = None

    def get_model_name(self) -> str:
        return "sensevoice/SenseVoiceSmall"

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Transcribe audio using SenseVoice with fixed-duration chunking.

        Splits audio into 30-second chunks to avoid OOM on long files.
        """
        model = self._get_model()

        logger.info(f"SenseVoice transcribing: {audio_path} on {settings.WHISPER_DEVICE}")

        segments = self._transcribe_with_fixed_chunks(model, audio_path)
        return self._aggregate_results(segments)

    def _transcribe_with_fixed_chunks(
        self,
        model,
        audio_path: str,
        chunk_sec: float = 30.0,
    ) -> list[TranscriptionSegment]:
        """Fallback: split audio into fixed-duration chunks and transcribe each."""
        import torch
        import torchaudio

        waveform, sample_rate = torchaudio.load(audio_path)
        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(sample_rate, 16000)
            waveform = resampler(waveform)
            sample_rate = 16000

        if waveform.dim() == 1:
            waveform = waveform.unsqueeze(0)

        total_samples = waveform.shape[1]
        chunk_samples = int(chunk_sec * sample_rate)
        all_segments: list[TranscriptionSegment] = []

        for start_sample in range(0, total_samples, chunk_samples):
            end_sample = min(start_sample + chunk_samples, total_samples)
            start_sec = start_sample / sample_rate
            end_sec = end_sample / sample_rate

            chunk_waveform = waveform[:, start_sample:end_sample]

            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                torchaudio.save(tmp_path, chunk_waveform, sample_rate)

            try:
                chunk_result = model.generate(
                    input=tmp_path,
                    language="auto",
                    use_itn=True,
                    ban_emo_unk=True,
                )

                parsed = self._parse_result(chunk_result)
                for seg in parsed.segments:
                    if seg.start == 0.0 and seg.end == 0.0:
                        seg.start = start_sec
                        seg.end = end_sec
                    else:
                        seg.start += start_sec
                        seg.end += start_sec
                    all_segments.append(seg)
            except Exception as e:
                logger.warning(f"Fixed chunk {start_sec:.0f}s-{end_sec:.0f}s failed: {e}")
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        return all_segments

    def _aggregate_results(self, segments: list[TranscriptionSegment]) -> TranscriptionResult:
        """Aggregate list of segments into a TranscriptionResult with language detection."""
        if not segments:
            return TranscriptionResult()

        # Sort by start time
        segments.sort(key=lambda s: s.start)

        word_count = sum(len(s.text.split()) for s in segments)
        detected_language = "unknown"

        logger.info(
            f"SenseVoice: {word_count} words, lang={detected_language}, "
            f"segments={len(segments)}"
        )

        return TranscriptionResult(
            segments=segments,
            language=detected_language,
            word_count=word_count,
        )

    def _parse_result(self, raw_result: list[dict[str, Any]]) -> TranscriptionResult:
        """Parse funasr AutoModel output into TranscriptionResult."""
        segments: list[TranscriptionSegment] = []
        word_count = 0
        detected_language = "unknown"

        if not raw_result:
            logger.warning("SenseVoice returned empty result")
            return TranscriptionResult()

        for utterance in raw_result:
            raw_text: str = utterance.get("text", "").strip()
            cleaned_text = self._clean_sensevoice_text(raw_text)

            if not cleaned_text:
                continue

            # Detect language from tags if present
            if detected_language == "unknown":
                lang_match = re.search(r"<\|([a-z]{2,3})\|>", raw_text)
                if lang_match:
                    detected_language = lang_match.group(1)

            # Try to extract timestamps (format varies by funasr version)
            timestamps = utterance.get("timestamp") or utterance.get("timestamp_list")
            text_word_count = len(cleaned_text.split()) if cleaned_text else 0

            if timestamps and isinstance(timestamps, list) and len(timestamps) > 0:
                for ts in timestamps:
                    if isinstance(ts, (list, tuple)) and len(ts) >= 2:
                        start, end = float(ts[0]), float(ts[1])
                        if end <= start:
                            continue
                        segments.append(TranscriptionSegment(
                            start=start,
                            end=end,
                            text=cleaned_text,
                            confidence=None,
                        ))
                word_count += text_word_count
            else:
                # No timestamps — fallback to single segment
                segments.append(TranscriptionSegment(
                    start=0.0,
                    end=0.0,
                    text=cleaned_text,
                    confidence=None,
                ))
                word_count += text_word_count

        logger.info(
            f"SenseVoice: {word_count} words, lang={detected_language}, "
            f"segments={len(segments)}"
        )

        return TranscriptionResult(
            segments=segments,
            language=detected_language,
            word_count=word_count,
        )

    @staticmethod
    def _clean_sensevoice_text(text: str) -> str:
        """Remove funasr/SenseVoice special tags from transcription text.

        SenseVoice returns text like: '<|zh|><|NEUTRAL|> 你好世界 <|nospeech|>'
        We strip all <|...|> tags and clean up whitespace.
        """
        cleaned = re.sub(r"<\|[^|]+\|>", "", text).strip()
        # Collapse multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    def _get_model(self):
        """Lazy-loaded singleton for SenseVoice AutoModel."""
        if self._model is None:
            from funasr import AutoModel

            device = settings.WHISPER_DEVICE
            logger.info(f"Loading SenseVoice model (iic/SenseVoiceSmall) on {device}")

            self._model = AutoModel(
                model="iic/SenseVoiceSmall",
                device=device,
                disable_update=True,
            )
            logger.info("SenseVoice model loaded")
        return self._model

    def _get_vad_model_safe(self):
        """Lazy-loaded singleton for VAD model.

        Attempts to load FSMN-VAD from ModelScope. Returns None if the model
        is unavailable (404 / not registered), so transcription can proceed
        without VAD segmentation.
        """
        if self._vad_model is None:
            try:
                from funasr import AutoModel

                device = settings.WHISPER_DEVICE
                logger.info(f"Loading VAD model (fsmn-vad) on {device}")

                self._vad_model = AutoModel(
                    model="iic/speech_fsmn_vad_zh-cn_16k-common-pytorch",
                    device=device,
                    disable_update=True,
                )
                logger.info("VAD model loaded")
            except Exception as e:
                logger.warning(f"VAD model unavailable, proceeding without it: {e}")
                self._vad_model = None  # ensure it stays None
        return self._vad_model


class SenseVoiceRemoteProvider(BaseTranscriber):
    """Transcription provider using SenseVoice via remote HTTP API.

    Useful when SenseVoice is deployed on a GPU server.
    Expects an OpenAI-compatible API or a simple POST audio → text endpoint.

    Configure via SENSEVOICE_API_URL environment variable.
    """

    def __init__(self):
        self._api_url = settings.SENSEVOICE_API_URL.rstrip("/")

    def get_model_name(self) -> str:
        return f"sensevoice/remote"

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Send audio file to remote SenseVoice API for transcription."""
        import httpx

        logger.info(f"SenseVoiceRemote: sending {audio_path} to {self._api_url}")

        with open(audio_path, "rb") as f:
            files = {"audio": f}
            response = httpx.post(
                f"{self._api_url}/transcribe",
                files=files,
                timeout=httpx.Timeout(1800.0, connect=30.0),
            )
            response.raise_for_status()
            data = response.json()

        return self._parse_api_response(data)

    def _parse_api_response(self, data: dict) -> TranscriptionResult:
        """Parse remote API response into TranscriptionResult.

        Expected API response format:
        {
            "segments": [{"start": 0.0, "end": 2.5, "text": "你好"}],
            "language": "zh",
            "word_count": 10
        }
        """
        segments_raw = data.get("segments", [])
        segments = [
            TranscriptionSegment(
                start=s.get("start", 0.0),
                end=s.get("end", 0.0),
                text=s.get("text", ""),
                confidence=s.get("confidence"),
            )
            for s in segments_raw
            if s.get("text", "").strip()
        ]

        return TranscriptionResult(
            segments=segments,
            language=data.get("language", "unknown"),
            word_count=data.get("word_count", sum(len(s.text.split()) for s in segments)),
        )
