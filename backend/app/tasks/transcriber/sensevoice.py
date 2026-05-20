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

    Long audio is split into fixed-duration chunks before upload so the remote
    GPU is not asked to transcribe an entire meeting in one request (OOM).
    """

    def __init__(self):
        self._api_url = settings.SENSEVOICE_API_URL.rstrip("/")
        self._chunk_seconds = max(60, int(settings.SENSEVOICE_CHUNK_SECONDS))

    def get_model_name(self) -> str:
        return "sensevoice/remote"

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        from app.utils.audio import get_audio_duration

        duration = get_audio_duration(audio_path)
        if duration <= self._chunk_seconds:
            logger.info(
                f"SenseVoiceRemote: single request ({duration:.0f}s) → {self._api_url}"
            )
            return self._parse_api_response(
                self._post_audio(audio_path),
                time_offset=0.0,
                chunk_duration=duration,
            )

        logger.info(
            f"SenseVoiceRemote: chunked transcribe {duration:.0f}s "
            f"in {self._chunk_seconds}s slices → {self._api_url}"
        )
        return self._transcribe_chunked(audio_path, duration)

    def _transcribe_chunked(self, audio_path: str, duration: float) -> TranscriptionResult:
        import os
        import subprocess
        import tempfile

        all_segments: list[TranscriptionSegment] = []
        language = "unknown"
        offset = 0.0
        chunk_idx = 0

        while offset < duration:
            chunk_len = min(self._chunk_seconds, duration - offset)
            chunk_idx += 1

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-ss", str(offset),
                        "-t", str(chunk_len),
                        "-i", audio_path,
                        "-ar", "16000", "-ac", "1",
                        tmp_path,
                    ],
                    check=True,
                    capture_output=True,
                )

                logger.info(
                    f"SenseVoiceRemote: chunk {chunk_idx} "
                    f"{offset:.0f}s–{offset + chunk_len:.0f}s"
                )
                data = self._post_audio(tmp_path)
                part = self._parse_api_response(
                    data,
                    time_offset=offset,
                    chunk_duration=chunk_len,
                )
                if part.language != "unknown":
                    language = part.language
                all_segments.extend(part.segments)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            offset += self._chunk_seconds

        word_count = sum(len(s.text.split()) for s in all_segments if s.text)
        logger.info(
            f"SenseVoiceRemote: done, {chunk_idx} chunks, "
            f"{word_count} words, {len(all_segments)} segments"
        )
        return TranscriptionResult(
            segments=all_segments,
            language=language,
            word_count=word_count,
        )

    def _post_audio(self, audio_path: str) -> dict:
        import os

        import httpx

        with open(audio_path, "rb") as f:
            response = httpx.post(
                f"{self._api_url}/transcribe",
                files={"audio": (os.path.basename(audio_path), f, "audio/wav")},
                timeout=httpx.Timeout(600.0, connect=30.0),
            )
            response.raise_for_status()
            return response.json()

    def _parse_api_response(
        self,
        data: dict,
        time_offset: float = 0.0,
        chunk_duration: float | None = None,
    ) -> TranscriptionResult:
        """Parse remote API JSON; apply time_offset for chunked transcription."""
        segments_raw = data.get("segments", [])
        if not segments_raw and data.get("text"):
            segments_raw = [{"start": 0.0, "end": 0.0, "text": data["text"]}]

        segments: list[TranscriptionSegment] = []
        for s in segments_raw:
            cleaned = SenseVoiceProvider._clean_sensevoice_text(s.get("text", ""))
            if not cleaned:
                continue

            start = float(s.get("start", 0.0))
            end = float(s.get("end", 0.0))
            if start == 0.0 and end == 0.0 and chunk_duration is not None:
                start = time_offset
                end = time_offset + chunk_duration
            else:
                start += time_offset
                end += time_offset
                if end <= start:
                    end = start + (chunk_duration or 1.0)

            segments.append(
                TranscriptionSegment(
                    start=start,
                    end=end,
                    text=cleaned,
                    confidence=s.get("confidence"),
                )
            )

        language = data.get("language", "unknown")
        word_count = sum(len(s.text.split()) for s in segments)

        return TranscriptionResult(
            segments=segments,
            language=language,
            word_count=word_count or data.get("word_count", 0),
        )
