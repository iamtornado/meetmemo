from __future__ import annotations

import uuid
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.errors import NotFoundError
from app.models.user import User
from app.schemas.summary import SummaryResponse, SummaryUpdate
from app.services.meeting_service import MeetingService
from app.services.summary_service import SummaryService
from app.utils.minutes_docx import build_formal_minutes_docx, minutes_export_filename

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


@router.get("/meetings/{meeting_id}/summary/minutes/export")
async def export_formal_minutes_docx(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    meeting_service = MeetingService(session)
    meeting = await meeting_service.get(meeting_id)
    if not meeting:
        raise NotFoundError("Meeting not found")

    summary_service = SummaryService(session)
    summary = await summary_service.get_by_meeting(meeting_id)
    if not summary or not summary.formal_minutes:
        raise NotFoundError("Formal minutes not found")

    docx_bytes = build_formal_minutes_docx(
        title=meeting.title or "会议纪要",
        formal_minutes=summary.formal_minutes,
    )
    filename = minutes_export_filename(meeting.title)
    ascii_name = filename.encode("ascii", "ignore").decode() or "minutes.docx"
    if not ascii_name.endswith(".docx"):
        ascii_name = "minutes.docx"
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return StreamingResponse(
        BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": disposition},
    )


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
