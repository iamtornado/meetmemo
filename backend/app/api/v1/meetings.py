from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.errors import NotFoundError
from app.config import settings
from app.models.user import User
from app.schemas.meeting import (
    MeetingCreate,
    MeetingListResponse,
    MeetingResponse,
    MeetingUpdate,
    ProcessRequest,
)
from app.services.meeting_service import MeetingService

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("", response_model=MeetingListResponse)
async def list_meetings(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    team_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = MeetingService(session)
    return await service.list_for_user(
        user_id=user.id,
        page=page,
        page_size=page_size,
        status=status,
        team_id=team_id,
    )


@router.post("", response_model=MeetingResponse)
async def create_meeting(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    team_id: uuid.UUID | None = Form(None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = MeetingService(session)

    # Save uploaded file
    ext = Path(file.filename or "audio.mp3").suffix
    file_id = uuid.uuid4()
    filename = f"{file_id}{ext}"
    file_path = Path(settings.STORAGE_PATH) / filename

    content = await file.read()
    file_path.write_bytes(content)

    meeting = await service.create(
        title=title or file.filename,
        audio_path=str(file_path),
        file_format=ext.lstrip("."),
        file_size=len(content),
        team_id=team_id,
        user_id=user.id,
    )
    return meeting


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = MeetingService(session)
    meeting = await service.get(meeting_id)
    if not meeting:
        raise NotFoundError("Meeting not found")
    return meeting


@router.put("/{meeting_id}", response_model=MeetingResponse)
async def update_meeting(
    meeting_id: uuid.UUID,
    body: MeetingUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = MeetingService(session)
    meeting = await service.get(meeting_id)
    if not meeting:
        raise NotFoundError("Meeting not found")
    return await service.update(meeting_id, body)


@router.delete("/{meeting_id}")
async def delete_meeting(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = MeetingService(session)
    meeting = await service.get(meeting_id)
    if not meeting:
        raise NotFoundError("Meeting not found")
    await service.delete(meeting_id)
    return {"message": "Meeting deleted"}


@router.post("/{meeting_id}/process")
async def process_meeting(
    meeting_id: uuid.UUID,
    body: ProcessRequest = ProcessRequest(),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = MeetingService(session)
    meeting = await service.get(meeting_id)
    if not meeting:
        raise NotFoundError("Meeting not found")

    if meeting.status == "processing":
        return {"message": "Already processing", "meeting_id": str(meeting_id)}

    from app.tasks.pipeline import run_meeting_pipeline
    from app.tasks.pipeline_helpers import mark_meeting_processing

    # Mark processing immediately so the UI updates without waiting for Celery worker pickup.
    mark_meeting_processing(str(meeting_id))

    run_meeting_pipeline.delay(
        str(meeting_id),
        whisper_model=body.whisper_model,
        run_diarize=body.diarize,
        run_summarize=body.summarize,
    )
    return {"message": "Processing started", "meeting_id": str(meeting_id)}


@router.post("/{meeting_id}/cancel")
async def cancel_meeting(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = MeetingService(session)
    await service.cancel_processing(meeting_id)
    return {"message": "Processing cancelled"}
