from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AttendeeSchema(BaseModel):
    speaker_id: str | None = None
    name: str
    is_guest: bool = False


class KeyPointSchema(BaseModel):
    topic: str | None = None
    description: str
    importance: int | None = None


class DecisionSchema(BaseModel):
    description: str
    made_by: str | None = None
    consensus: bool = True


class ActionItemSchema(BaseModel):
    description: str
    assignee: str | None = None
    due_date: datetime | None = None
    status: str = "pending"


class SummaryResponse(BaseModel):
    id: uuid.UUID
    meeting_id: uuid.UUID
    model_used: str
    ai_title: str | None
    ai_date: datetime | None
    next_agenda: str | None
    additional_notes: str | None
    formal_minutes: str | None = None
    created_at: datetime
    updated_at: datetime
    attendees: list[AttendeeSchema] = []
    key_points: list[KeyPointSchema] = []
    decisions: list[DecisionSchema] = []
    action_items: list[ActionItemSchema] = []

    model_config = {"from_attributes": True}


class SummaryUpdate(BaseModel):
    ai_title: str | None = None
    ai_date: datetime | None = None
    next_agenda: str | None = None
    additional_notes: str | None = None
    attendees: list[AttendeeSchema] | None = None
    key_points: list[KeyPointSchema] | None = None
    decisions: list[DecisionSchema] | None = None
    action_items: list[ActionItemSchema] | None = None
