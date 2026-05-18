from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import NotFoundError, ConflictError
from app.models.team import Team, TeamMember
from app.schemas.team import TeamCreate, TeamResponse, TeamUpdate, TeamMemberResponse


class TeamService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[TeamResponse]:
        result = await self.session.execute(
            select(Team)
            .join(TeamMember)
            .where(TeamMember.user_id == user_id)
            .options(selectinload(Team.members))
            .order_by(Team.created_at.desc())
        )
        return result.scalars().all()

    async def create(self, body: TeamCreate, user_id: uuid.UUID) -> Team:
        team = Team(name=body.name, description=body.description, created_by=user_id)
        self.session.add(team)
        await self.session.flush()

        # Add creator as owner
        member = TeamMember(user_id=user_id, team_id=team.id, role="owner")
        self.session.add(member)
        await self.session.flush()

        return team

    async def get(self, team_id: uuid.UUID) -> Team | None:
        result = await self.session.execute(
            select(Team)
            .where(Team.id == team_id)
            .options(selectinload(Team.members))
        )
        return result.scalar_one_or_none()

    async def update(self, team_id: uuid.UUID, body: TeamUpdate) -> Team:
        result = await self.session.execute(
            select(Team).where(Team.id == team_id)
        )
        team = result.scalar_one_or_none()
        if not team:
            raise NotFoundError("Team not found")

        if body.name is not None:
            team.name = body.name
        if body.description is not None:
            team.description = body.description

        await self.session.flush()
        return team

    async def delete(self, team_id: uuid.UUID):
        result = await self.session.execute(
            select(Team).where(Team.id == team_id)
        )
        team = result.scalar_one_or_none()
        if team:
            await self.session.delete(team)
            await self.session.flush()

    async def add_member(self, team_id: uuid.UUID, user_id: uuid.UUID, role: str = "viewer"):
        # Check if already member
        result = await self.session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
            )
        )
        if result.scalar_one_or_none():
            raise ConflictError("User is already a member")

        member = TeamMember(user_id=user_id, team_id=team_id, role=role)
        self.session.add(member)
        await self.session.flush()
        return member

    async def remove_member(self, team_id: uuid.UUID, user_id: uuid.UUID):
        result = await self.session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            await self.session.delete(member)
            await self.session.flush()
