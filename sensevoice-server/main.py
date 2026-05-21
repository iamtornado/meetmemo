"""MeetMemo SenseVoice ASR API — official FunASR path (VAD + merge_vad).

Aligned with FunAudioLLM/SenseVoice demo1.py:
  - fsmn-vad inside AutoModel
  - merge_vad + batch_size_s for long audio
  - rich_transcription_postprocess for display text

MeetMemo worker should send the full normalized WAV in one request when /health
reports vad_enabled=true (no client-side 300s ffmpeg slicing).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile

from segment_merge import merge_to_sentence_level, needs_sentence_merge

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_model = None

# --- Tunables (env) ---
VAD_MODEL = os.environ.get("SENSEVOICE_VAD_MODEL", "fsmn-vad")
VAD_MAX_SINGLE_SEGMENT_MS = int(os.environ.get("SENSEVOICE_VAD_MAX_SEGMENT_MS", "30000"))
MERGE_LENGTH_S = int(os.environ.get("SENSEVOICE_MERGE_LENGTH_S", "15"))
BATCH_SIZE_S = int(os.environ.get("SENSEVOICE_BATCH_SIZE_S", "60"))
OUTPUT_TIMESTAMP = os.environ.get("SENSEVOICE_OUTPUT_TIMESTAMP", "true").lower() in (
    "1",
    "true",
    "yes",
)


def get_model():
    global _model
    if _model is not None:
        return _model

    from funasr import AutoModel

    os.environ.setdefault("MODELSCOPE_CACHE", "/data/modelscope_cache")
    device = os.environ.get("SENSEVOICE_DEVICE", "cuda:0")

    logger.info(
        "Loading SenseVoice + VAD (vad=%s, max_segment_ms=%s, device=%s)...",
        VAD_MODEL,
        VAD_MAX_SINGLE_SEGMENT_MS,
        device,
    )
    t0 = time.time()
    _model = AutoModel(
        model="iic/SenseVoiceSmall",
        vad_model=VAD_MODEL,
        vad_kwargs={"max_single_segment_time": VAD_MAX_SINGLE_SEGMENT_MS},
        device=device,
        disable_update=True,
        hub="ms",
    )
    logger.info("SenseVoice+VAD loaded in %.1fs", time.time() - t0)
    return _model


_TAG_RE = re.compile(r"<\|[^|]+\|>")


def _clean_tags(text: str) -> str:
    cleaned = _TAG_RE.sub("", text or "").strip()
    return re.sub(r"\s+", " ", cleaned).strip()


def _postprocess_text(raw: str) -> str:
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess

        return rich_transcription_postprocess(raw)
    except Exception as exc:
        logger.warning("rich_transcription_postprocess failed: %s", exc)
        return _clean_tags(raw)


def _to_seconds(value: float) -> float:
    """FunASR may return ms (>1000) or seconds."""
    if value > 10000:
        return value / 1000.0
    if value > 300:
        return value / 1000.0
    return float(value)


def _segments_from_sentence_info(sentence_info: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for item in sentence_info:
        text = _clean_tags(str(item.get("text", "")))
        if not text:
            continue
        start = _to_seconds(float(item.get("start", 0)))
        end = _to_seconds(float(item.get("end", 0)))
        if end <= start:
            end = start + 1.0
        segments.append({"start": start, "end": end, "text": text})
    return segments


def _segments_from_timestamp(
    text: str, timestamp: list, words: list | None = None
) -> list[dict[str, Any]]:
    """Build segments from CTC timestamp list when sentence_info is absent."""
    segments: list[dict[str, Any]] = []
    if not timestamp:
        return segments

    # timestamp entries: [start, end] in ms or [token, start, end]
    parsed: list[tuple[float, float]] = []
    for ts in timestamp:
        if isinstance(ts, (list, tuple)):
            if len(ts) >= 3 and not isinstance(ts[0], (int, float)):
                _, a, b = ts[0], float(ts[1]), float(ts[2])
            elif len(ts) >= 2:
                a, b = float(ts[0]), float(ts[1])
            else:
                continue
            parsed.append((_to_seconds(a), _to_seconds(b)))

    if not parsed:
        return segments

    # One block per VAD merge unit — use full text if we cannot align words
    if words and len(words) == len(parsed):
        for i, (start, end) in enumerate(parsed):
            w = _clean_tags(str(words[i]))
            if w:
                segments.append({"start": start, "end": end, "text": w})
    elif text:
        segments.append(
            {
                "start": parsed[0][0],
                "end": parsed[-1][1],
                "text": text,
            }
        )
    return segments


def parse_generate_result(result: Any) -> tuple[str, list[dict[str, Any]], str]:
    """Normalize funasr generate() output to (full_text, segments, language)."""
    if not result:
        return "", [], "unknown"

    item = result[0] if isinstance(result, list) else result
    if not isinstance(item, dict):
        return _postprocess_text(str(item)), [], "unknown"

    raw_text = str(item.get("text", ""))
    full_text = _postprocess_text(raw_text)

    segments: list[dict[str, Any]] = []
    sentence_info = item.get("sentence_info")
    if isinstance(sentence_info, list) and sentence_info:
        segments = _segments_from_sentence_info(sentence_info)

    if not segments:
        ts = item.get("timestamp")
        words = item.get("words")
        if ts:
            segments = _segments_from_timestamp(full_text, ts, words)

    if not segments and full_text:
        segments = [{"start": 0.0, "end": 0.0, "text": full_text}]

    raw_count = len(segments)
    if needs_sentence_merge(segments):
        segments = merge_to_sentence_level(
            segments,
            max_duration_sec=float(MERGE_LENGTH_S),
        )
        logger.info("Merged %d micro-segments → %d sentence segments", raw_count, len(segments))

    lang = "unknown"
    lang_match = re.search(r"<\|([a-z]{2,3})\|>", raw_text)
    if lang_match:
        lang = lang_match.group(1)

    return full_text, segments, lang


def transcribe_file(path: str) -> dict[str, Any]:
    model = get_model()
    t0 = time.time()

    result = model.generate(
        input=path,
        cache={},
        language="auto",
        use_itn=True,
        ban_emo_unk=True,
        batch_size_s=BATCH_SIZE_S,
        merge_vad=True,
        merge_length_s=MERGE_LENGTH_S,
        output_timestamp=OUTPUT_TIMESTAMP,
    )

    elapsed = time.time() - t0
    full_text, segments, language = parse_generate_result(result)
    word_count = len(full_text.replace(" ", "")) if full_text else 0

    logger.info(
        "Transcribed %s: %d chars, %d segments, %.1fs",
        path,
        word_count,
        len(segments),
        elapsed,
    )

    return {
        "text": full_text,
        "word_count": word_count,
        "language": language if language != "unknown" else "zh",
        "segments": segments,
        "model_used": "sensevoice/SenseVoiceSmall+vad",
        "elapsed_seconds": round(elapsed, 2),
        "vad_enabled": True,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SenseVoice ASR server (VAD mode)...")
    try:
        get_model()
    except Exception as exc:
        logger.error("Failed to load model: %s", exc)
    yield


app = FastAPI(title="MeetMemo SenseVoice ASR", version="2.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    import torch

    return {
        "status": "ok",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "model_loaded": _model is not None,
        "vad_enabled": True,
        "merge_vad": True,
        "batch_size_s": BATCH_SIZE_S,
        "merge_length_s": MERGE_LENGTH_S,
        "vad_max_segment_ms": VAD_MAX_SINGLE_SEGMENT_MS,
    }


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    if _model is None:
        try:
            get_model()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Model not loaded: {exc}") from exc

    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(await audio.read())

    try:
        return transcribe_file(tmp_path)
    except Exception as exc:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8003"))
    uvicorn.run(app, host=host, port=port, workers=1)
