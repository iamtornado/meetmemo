from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TeamCreate(BaseModel):
    name: str
    description: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class TeamMemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID
    created_at: datetime
    members: list[TeamMemberResponse] = []

    model_config = {"from_attributes": True}


class TeamMemberAdd(BaseModel):
    user_id: uuid.UUID
    role: str = "viewer"
