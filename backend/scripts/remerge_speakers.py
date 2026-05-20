"""Re-run diarization merge for an existing meeting transcript."""
from __future__ import annotations

import sys
import uuid

from app.database import sync_session_factory
from app.models.meeting import Meeting
from app.models.transcript import Transcript, TranscriptSegment
from app.tasks.diarizer.factory import get_diarizer
from app.utils.speaker_merge import merge_diarization_with_transcript


def main(meeting_id: str) -> None:
    mid = uuid.UUID(meeting_id)
    with sync_session_factory() as session:
        meeting = session.query(Meeting).filter(Meeting.id == mid).first()
        if not meeting:
            print("meeting not found")
            return

        transcript = session.query(Transcript).filter(Transcript.meeting_id == mid).first()
        if not transcript:
            print("transcript not found")
            return

        preprocessed = f"/data/uploads/preprocessed/{meeting_id}_normalized.wav"
        audio_path = preprocessed
        from pathlib import Path

        if not Path(preprocessed).exists():
            audio_path = meeting.audio_path
            print(f"using original audio: {audio_path}")

        segments = [
            {
                "start": s.start_time,
                "end": s.end_time,
                "text": s.text,
                "confidence": s.confidence,
            }
            for s in sorted(transcript.segments, key=lambda x: x.seq_number)
        ]
        print(f"transcript segments: {len(segments)}")

        diarizer = get_diarizer()
        print(f"running diarizer: {diarizer.get_model_name()} ...")
        result = diarizer.diarize(audio_path)
        print(
            f"pyannote: {len(result.speaker_segments)} slices, "
            f"{result.num_speakers} speakers"
        )

        merged = merge_diarization_with_transcript(segments, result.speaker_segments)

        for s in list(transcript.segments):
            session.delete(s)
        session.flush()

        for i, seg in enumerate(merged):
            session.add(
                TranscriptSegment(
                    transcript_id=transcript.id,
                    seq_number=i,
                    speaker_id=seg.get("speaker_id"),
                    speaker_name=None,
                    start_time=seg["start"],
                    end_time=seg["end"],
                    text=seg["text"],
                    confidence=seg.get("confidence"),
                )
            )

        session.commit()

        from collections import Counter

        counts = Counter(seg.get("speaker_id") or "None" for seg in merged)
        print("speaker distribution:")
        for sp, cnt in counts.most_common():
            print(f"  {sp}: {cnt}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "09c206cb-8623-4296-a4b9-7b259e291175")
