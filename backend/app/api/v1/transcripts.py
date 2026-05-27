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
from app.schemas.transcript import SpeakerRename, TranscriptResponse
from app.services.meeting_service import MeetingService
from app.services.transcript_service import TranscriptService
from app.utils.transcript_docx import build_transcript_docx, transcript_export_filename

router = APIRouter(tags=["transcripts"])


@router.get("/meetings/{meeting_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = TranscriptService(session)
    transcript = await service.get_by_meeting(meeting_id)
    if not transcript:
        raise NotFoundError("Transcript not found")
    return transcript


@router.get("/meetings/{meeting_id}/transcript/export")
async def export_transcript_docx(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    meeting_service = MeetingService(session)
    meeting = await meeting_service.get(meeting_id)
    if not meeting:
        raise NotFoundError("Meeting not found")

    transcript_service = TranscriptService(session)
    transcript = await transcript_service.get_by_meeting(meeting_id)
    if not transcript:
        raise NotFoundError("Transcript not found")

    docx_bytes = build_transcript_docx(
        title=meeting.title or "Meeting Transcript",
        transcript=transcript,
        meeting_date=meeting.date,
    )
    filename = transcript_export_filename(meeting.title, str(meeting_id))
    ascii_name = filename.encode("ascii", "ignore").decode() or "transcript.docx"
    if not ascii_name.endswith(".docx"):
        ascii_name = "transcript.docx"
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return StreamingResponse(
        BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": disposition},
    )


@router.put("/meetings/{meeting_id}/transcript/speakers")
async def rename_speakers(
    meeting_id: uuid.UUID,
    body: SpeakerRename,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = TranscriptService(session)
    await service.rename_speakers(meeting_id, body.mappings)
    return {"message": "Speakers renamed"}
