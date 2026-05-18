from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import NotFoundError
from app.models.meeting import Meeting
from app.schemas.meeting import MeetingListResponse, MeetingResponse, MeetingUpdate


class MeetingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        team_id: uuid.UUID | None = None,
    ) -> MeetingListResponse:
        query = select(Meeting).where(Meeting.created_by == user_id)
        count_query = select(func.count(Meeting.id)).where(Meeting.created_by == user_id)

        if status:
            query = query.where(Meeting.status == status)
            count_query = count_query.where(Meeting.status == status)
        if team_id:
            query = query.where(Meeting.team_id == team_id)
            count_query = count_query.where(Meeting.team_id == team_id)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = (
            query
            .order_by(Meeting.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)

        return MeetingListResponse(
            items=result.scalars().all(),
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total > 0 else 0,
        )

    async def create(
        self,
        title: str | None,
        audio_path: str,
        file_format: str,
        file_size: int,
        user_id: uuid.UUID,
        team_id: uuid.UUID | None = None,
    ) -> Meeting:
        meeting = Meeting(
            title=title,
            audio_path=audio_path,
            file_format=file_format,
            file_size=file_size,
            created_by=user_id,
            team_id=team_id,
            status="uploaded",
        )
        self.session.add(meeting)
        await self.session.flush()
        return meeting

    async def get(self, meeting_id: uuid.UUID) -> Meeting | None:
        result = await self.session.execute(
            select(Meeting)
            .where(Meeting.id == meeting_id)
            .options(
                selectinload(Meeting.transcript),
                selectinload(Meeting.summary),
            )
        )
        return result.scalar_one_or_none()

    async def update(self, meeting_id: uuid.UUID, body: MeetingUpdate) -> Meeting:
        result = await self.session.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )
        meeting = result.scalar_one_or_none()
        if not meeting:
            raise NotFoundError("Meeting not found")

        if body.title is not None:
            meeting.title = body.title
        if body.date is not None:
            meeting.date = body.date
        if body.duration_seconds is not None:
            meeting.duration_seconds = body.duration_seconds

        await self.session.flush()
        return meeting

    async def delete(self, meeting_id: uuid.UUID):
        result = await self.session.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )
        meeting = result.scalar_one_or_none()
        if meeting:
            await self.session.delete(meeting)
            await self.session.flush()

    async def cancel_processing(self, meeting_id: uuid.UUID):
        result = await self.session.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )
        meeting = result.scalar_one_or_none()
        if meeting:
            meeting.status = "cancelled"
            await self.session.flush()
