from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

    async def rename_speakers(self, meeting_id: uuid.UUID, mappings: dict[str, str]):
        result = await self.session.execute(
            select(Transcript).where(Transcript.meeting_id == meeting_id)
        )
        transcript = result.scalar_one_or_none()
        if not transcript:
            return

        # Update all matching segments
        for old_id, new_name in mappings.items():
            stmt = (
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.transcript_id == transcript.id,
                    TranscriptSegment.speaker_id == old_id,
                )
            )
            segments = (await self.session.execute(stmt)).scalars().all()
            for seg in segments:
                seg.speaker_name = new_name

        await self.session.flush()
