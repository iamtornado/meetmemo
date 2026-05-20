from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AuthGroupMappingResponse(BaseModel):
    id: uuid.UUID
    auth_provider: str
    group_name: str
    mapped_role: str
    team_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthGroupMappingCreate(BaseModel):
    auth_provider: str = "ldap"
    group_name: str = Field(..., min_length=1, max_length=255)
    mapped_role: str = Field(..., pattern="^(admin|editor|member|viewer)$")
    team_id: uuid.UUID | None = None
