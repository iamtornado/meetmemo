from __future__ import annotations

import logging
import re

from app.config import settings
from app.tasks.transcriber.base import TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)

_punc_model = None

# Already punctuated enough — skip model call
_PUNCT_RE = re.compile(r"[，。！？；、,.!?;]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；!?])\s*")


def _get_punc_model():
    global _punc_model
    if _punc_model is None:
        from funasr import AutoModel

        model_id = settings.PUNCTUATION_MODEL
        logger.info(f"Loading punctuation model: {model_id}")
        _punc_model = AutoModel(model=model_id, disable_update=True)
        logger.info("Punctuation model loaded")
    return _punc_model


def _needs_punctuation(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) < 8:
        return False
    punct_count = len(_PUNCT_RE.findall(stripped))
    # Fewer than one punct per ~40 CJK chars → likely raw ASR
    return punct_count < max(1, len(stripped) // 40)


def add_punctuation(text: str) -> str:
    """Restore Chinese punctuation using FunASR ct-punc."""
    text = text.strip()
    if not text or not _needs_punctuation(text):
        return text

    try:
        model = _get_punc_model()
        result = model.generate(input=text)
        if result and isinstance(result, list) and result[0].get("text"):
            return result[0]["text"].strip()
    except Exception as e:
        logger.warning(f"Punctuation model failed, using raw text: {e}")

    return text


def _split_segment(seg: TranscriptionSegment) -> list[TranscriptionSegment]:
    """Split a long segment into sentence-level pieces after punctuation."""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(seg.text) if p.strip()]
    if len(parts) <= 1:
        return [seg]

    duration = max(seg.end - seg.start, 1.0)
    total_chars = sum(len(p) for p in parts) or 1
    out: list[TranscriptionSegment] = []
    t = seg.start

    for i, part in enumerate(parts):
        frac = len(part) / total_chars
        chunk_dur = duration * frac
        if i == len(parts) - 1:
            end = seg.end
        else:
            end = t + chunk_dur
        out.append(
            TranscriptionSegment(
                start=t,
                end=end,
                text=part,
                confidence=seg.confidence,
            )
        )
        t = end

    return out


def count_text_units(text: str, language: str) -> int:
    lang = (language or "").lower()
    if lang in ("zh", "yue", "ja", "ko", "unknown"):
        # Chinese etc.: character count is more meaningful than space-split
        return len(re.sub(r"\s+", "", text))
    return len(text.split())


def apply_punctuation_to_result(result: TranscriptionResult) -> TranscriptionResult:
    """Add punctuation and split long segments for readability."""
    if not settings.PUNCTUATION_ENABLED:
        return result

    new_segments: list[TranscriptionSegment] = []
    for seg in result.segments:
        if not seg.text.strip():
            continue
        punctuated = add_punctuation(seg.text)
        refined = TranscriptionSegment(
            start=seg.start,
            end=seg.end,
            text=punctuated,
            confidence=seg.confidence,
        )
        new_segments.extend(_split_segment(refined))

    word_count = sum(count_text_units(s.text, result.language) for s in new_segments)

    logger.info(
        f"Punctuation applied: {len(result.segments)} → {len(new_segments)} segments"
    )

    return TranscriptionResult(
        segments=new_segments,
        language=result.language,
        word_count=word_count,
    )
