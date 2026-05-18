from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.models.user import User
from app.models.meeting import Meeting
from app.models.auth import AuthGroupMapping
from app.schemas.user import UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: uuid.UUID,
    role: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        from app.api.errors import NotFoundError
        raise NotFoundError("User not found")

    user.role = role
    await session.flush()
    return {"message": f"User role updated to {role}"}


@router.get("/stats")
async def get_stats(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    user_count = (await session.execute(select(func.count(User.id)))).scalar()
    meeting_count = (await session.execute(select(func.count(Meeting.id)))).scalar()
    return {
        "total_users": user_count,
        "total_meetings": meeting_count,
    }


@router.get("/auth/mappings")
async def list_auth_mappings(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    result = await session.execute(select(AuthGroupMapping))
    return result.scalars().all()


@router.post("/auth/mappings")
async def create_auth_mapping(
    auth_provider: str,
    group_name: str,
    mapped_role: str,
    team_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    mapping = AuthGroupMapping(
        auth_provider=auth_provider,
        group_name=group_name,
        mapped_role=mapped_role,
        team_id=team_id,
    )
    session.add(mapping)
    await session.flush()
    return mapping
