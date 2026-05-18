from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    meeting_id: uuid.UUID
    title: str | None
    date: datetime | None
    status: str
    team_id: uuid.UUID | None
    created_at: datetime
    matched_text: str  # Snippet of matched content
    match_type: str  # "transcript", "summary", "title"


class SearchResponse(BaseModel):
    items: list[SearchResultItem]
    total: int
    page: int
    page_size: int
