from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.search import SearchResponse
from app.services.search_service import SearchService

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    team_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = SearchService(session)
    return await service.search(
        query=q,
        user_id=str(user.id),
        team_id=team_id,
        page=page,
        page_size=page_size,
    )
