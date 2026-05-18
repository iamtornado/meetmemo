from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TranscriptSegmentResponse(BaseModel):
    id: int
    seq_number: int
    speaker_id: str | None
    speaker_name: str | None
    start_time: float
    end_time: float
    text: str
    confidence: float | None

    model_config = {"from_attributes": True}


class TranscriptResponse(BaseModel):
    id: uuid.UUID
    meeting_id: uuid.UUID
    language: str | None
    model_used: str | None
    word_count: int
    created_at: datetime
    segments: list[TranscriptSegmentResponse] = []

    model_config = {"from_attributes": True}


class SpeakerRename(BaseModel):
    mappings: dict[str, str]  # speaker_id -> new_name
