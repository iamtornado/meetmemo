from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.errors import NotFoundError, ForbiddenError
from app.models.user import User
from app.schemas.team import TeamCreate, TeamResponse, TeamUpdate, TeamMemberAdd, TeamMemberResponse
from app.services.team_service import TeamService

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamResponse])
async def list_teams(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = TeamService(session)
    return await service.list_for_user(user.id)


@router.post("", response_model=TeamResponse)
async def create_team(
    body: TeamCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = TeamService(session)
    return await service.create(body, user.id)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = TeamService(session)
    team = await service.get(team_id)
    if not team:
        raise NotFoundError("Team not found")
    return team


@router.put("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = TeamService(session)
    team = await service.get(team_id)
    if not team:
        raise NotFoundError("Team not found")
    return await service.update(team_id, body)


@router.delete("/{team_id}")
async def delete_team(
    team_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = TeamService(session)
    team = await service.get(team_id)
    if not team:
        raise NotFoundError("Team not found")
    await service.delete(team_id)
    return {"message": "Team deleted"}


@router.post("/{team_id}/members")
async def add_member(
    team_id: uuid.UUID,
    body: TeamMemberAdd,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = TeamService(session)
    return await service.add_member(team_id, body.user_id, body.role)


@router.delete("/{team_id}/members/{user_id}")
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = TeamService(session)
    await service.remove_member(team_id, user_id)
    return {"message": "Member removed"}
