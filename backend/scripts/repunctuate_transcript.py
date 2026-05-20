"""One-off: re-apply punctuation to an existing meeting transcript."""
from __future__ import annotations

import sys
import uuid

from app.database import sync_session_factory
from app.models.transcript import Transcript, TranscriptSegment
from app.tasks.transcriber.base import TranscriptionResult, TranscriptionSegment as TSeg
from app.utils.punctuation import apply_punctuation_to_result


def main(meeting_id: str) -> None:
    mid = uuid.UUID(meeting_id)
    with sync_session_factory() as session:
        t = session.query(Transcript).filter(Transcript.meeting_id == mid).first()
        if not t:
            print("transcript not found")
            return

        old_segs = sorted(t.segments, key=lambda s: s.seq_number)
        result = apply_punctuation_to_result(
            TranscriptionResult(
                segments=[
                    TSeg(s.start_time, s.end_time, s.text, s.confidence)
                    for s in old_segs
                ],
                language=t.language or "zh",
                word_count=t.word_count,
            )
        )

        def speaker_for(start: float, end: float) -> str | None:
            best_id, best_ov = None, 0.0
            for o in old_segs:
                ov = max(0.0, min(end, o.end_time) - max(start, o.start_time))
                if ov > best_ov:
                    best_ov, best_id = ov, o.speaker_id
            return best_id

        for s in list(old_segs):
            session.delete(s)
        session.flush()

        for i, seg in enumerate(result.segments):
            session.add(
                TranscriptSegment(
                    transcript_id=t.id,
                    seq_number=i,
                    speaker_id=speaker_for(seg.start, seg.end),
                    speaker_name=None,
                    start_time=seg.start,
                    end_time=seg.end,
                    text=seg.text,
                    confidence=seg.confidence,
                )
            )

        t.word_count = result.word_count
        if t.model_used and "+ct-punc" not in (t.model_used or ""):
            t.model_used = f"{t.model_used}+ct-punc"
        session.commit()
        print(f"OK: {len(old_segs)} -> {len(result.segments)} segments")
        if result.segments:
            print(result.segments[0].text[:120])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "09c206cb-8623-4296-a4b9-7b259e291175")
