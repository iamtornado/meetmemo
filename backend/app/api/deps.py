from __future__ import annotations

import uuid

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import decode_access_token
from app.database import get_session
from app.models.user import User
from app.api.errors import AuthError, ForbiddenError


async def get_current_user(
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization:
        raise AuthError("Missing authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("Invalid authorization scheme, use Bearer")

    payload = decode_access_token(token)
    if payload is None:
        raise AuthError("Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Invalid token payload")

    result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise AuthError("User not found or inactive")

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise ForbiddenError("Admin access required")
    return user


async def require_editor(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "editor"):
        raise ForbiddenError("Editor or admin access required")
    return user
