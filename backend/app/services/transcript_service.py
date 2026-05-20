from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.summary import Summary, SummaryAttendee
from app.models.transcript import Transcript, TranscriptSegment


class TranscriptService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_meeting(self, meeting_id: uuid.UUID) -> Transcript | None:
        result = await self.session.execute(
            select(Transcript)
            .where(Transcript.meeting_id == meeting_id)
            .options(selectinload(Transcript.segments))
        )
        return result.scalar_one_or_none()

    async def rename_speakers(self, meeting_id: uuid.UUID, mappings: dict[str, str]) -> int:
        """Apply speaker_id -> display name mappings to transcript and summary."""
        result = await self.session.execute(
            select(Transcript).where(Transcript.meeting_id == meeting_id)
        )
        transcript = result.scalar_one_or_none()
        if not transcript:
            return 0

        updated = 0
        for old_id, new_name in mappings.items():
            new_name = (new_name or "").strip()
            if not new_name or new_name == old_id:
                continue

            stmt = select(TranscriptSegment).where(
                TranscriptSegment.transcript_id == transcript.id,
                TranscriptSegment.speaker_id == old_id,
            )
            segments = (await self.session.execute(stmt)).scalars().all()
            for seg in segments:
                seg.speaker_name = new_name
                updated += 1

            summary_result = await self.session.execute(
                select(Summary).where(Summary.meeting_id == meeting_id)
            )
            summary = summary_result.scalar_one_or_none()
            if summary:
                attendees_result = await self.session.execute(
                    select(SummaryAttendee).where(SummaryAttendee.summary_id == summary.id)
                )
                for attendee in attendees_result.scalars().all():
                    if attendee.speaker_id == old_id or attendee.name == old_id:
                        attendee.speaker_id = old_id
                        attendee.name = new_name

        await self.session.flush()
        return updated
