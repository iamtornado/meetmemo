from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.errors import NotFoundError
from app.models.user import User
from app.schemas.transcript import SpeakerRename, TranscriptResponse
from app.services.transcript_service import TranscriptService

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
