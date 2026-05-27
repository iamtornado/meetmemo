from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class MeetingCreate(BaseModel):
    title: str | None = None
    team_id: uuid.UUID | None = None


class MeetingUpdate(BaseModel):
    title: str | None = None
    date: datetime | None = None
    duration_seconds: int | None = None
    meeting_location: str | None = None
    host: str | None = None
    recorder_unit: str | None = None


class MeetingResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    date: datetime | None
    duration_seconds: int | None
    status: str
    team_id: uuid.UUID | None
    created_by: uuid.UUID
    audio_path: str
    file_format: str
    file_size: int
    error_message: str | None
    processing_started_at: datetime | None
    processing_completed_at: datetime | None
    meeting_location: str | None = None
    host: str | None = None
    recorder_unit: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MeetingListResponse(BaseModel):
    items: list[MeetingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProcessRequest(BaseModel):
    whisper_model: str | None = None
    diarize: bool = True
    summarize: bool = True
