from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.summary import (
    Summary,
    SummaryAttendee,
    SummaryKeyPoint,
    SummaryDecision,
    SummaryActionItem,
)
from app.schemas.summary import SummaryUpdate


class SummaryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_meeting(self, meeting_id: uuid.UUID) -> Summary | None:
        result = await self.session.execute(
            select(Summary)
            .where(Summary.meeting_id == meeting_id)
            .options(
                selectinload(Summary.attendees),
                selectinload(Summary.key_points),
                selectinload(Summary.decisions),
                selectinload(Summary.action_items),
            )
        )
        return result.scalar_one_or_none()

    async def update(self, meeting_id: uuid.UUID, body: SummaryUpdate) -> Summary | None:
        result = await self.session.execute(
            select(Summary).where(Summary.meeting_id == meeting_id)
        )
        summary = result.scalar_one_or_none()
        if not summary:
            return None

        if body.ai_title is not None:
            summary.ai_title = body.ai_title
        if body.ai_date is not None:
            summary.ai_date = body.ai_date
        if body.next_agenda is not None:
            summary.next_agenda = body.next_agenda
        if body.additional_notes is not None:
            summary.additional_notes = body.additional_notes

        # Replace child entities if provided
        if body.attendees is not None:
            existing = await self.session.execute(
                select(SummaryAttendee).where(SummaryAttendee.summary_id == summary.id)
            )
            for a in existing.scalars().all():
                await self.session.delete(a)
            for a in body.attendees:
                self.session.add(SummaryAttendee(
                    summary_id=summary.id,
                    speaker_id=a.speaker_id,
                    name=a.name,
                    is_guest=a.is_guest,
                ))

        if body.key_points is not None:
            existing = await self.session.execute(
                select(SummaryKeyPoint).where(SummaryKeyPoint.summary_id == summary.id)
            )
            for k in existing.scalars().all():
                await self.session.delete(k)
            for k in body.key_points:
                self.session.add(SummaryKeyPoint(
                    summary_id=summary.id,
                    topic=k.topic,
                    description=k.description,
                    importance=k.importance,
                ))

        if body.decisions is not None:
            existing = await self.session.execute(
                select(SummaryDecision).where(SummaryDecision.summary_id == summary.id)
            )
            for d in existing.scalars().all():
                await self.session.delete(d)
            for d in body.decisions:
                self.session.add(SummaryDecision(
                    summary_id=summary.id,
                    description=d.description,
                    made_by=d.made_by,
                    consensus=d.consensus,
                ))

        if body.action_items is not None:
            existing = await self.session.execute(
                select(SummaryActionItem).where(SummaryActionItem.summary_id == summary.id)
            )
            for a in existing.scalars().all():
                await self.session.delete(a)
            for a in body.action_items:
                self.session.add(SummaryActionItem(
                    summary_id=summary.id,
                    description=a.description,
                    assignee=a.assignee,
                    due_date=a.due_date,
                    status=a.status,
                ))

        await self.session.flush()
        return summary
