from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.errors import NotFoundError
from app.models.user import User
from app.schemas.summary import SummaryResponse, SummaryUpdate
from app.services.summary_service import SummaryService

router = APIRouter(tags=["summaries"])


@router.get("/meetings/{meeting_id}/summary", response_model=SummaryResponse)
async def get_summary(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = SummaryService(session)
    summary = await service.get_by_meeting(meeting_id)
    if not summary:
        raise NotFoundError("Summary not found")
    return summary


@router.post("/meetings/{meeting_id}/summary/regenerate")
async def regenerate_summary(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    from app.tasks.pipeline import run_summarization

    run_summarization.delay(str(meeting_id))
    return {"message": "Summary regeneration started"}


@router.put("/meetings/{meeting_id}/summary", response_model=SummaryResponse)
async def update_summary(
    meeting_id: uuid.UUID,
    body: SummaryUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = SummaryService(session)
    summary = await service.update(meeting_id, body)
    if not summary:
        raise NotFoundError("Summary not found")
    return summary
