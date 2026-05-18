from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AuthError, ConflictError
from app.config import settings
from app.models.auth import RefreshToken
from app.models.user import User
from app.schemas.user import TokenResponse, UserResponse
from app.auth.middleware import create_access_token, create_refresh_token


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def register(
        self, email: str, password: str, display_name: str, role: str = "member"
    ) -> User:
        result = await self.session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise ConflictError("Email already registered")

        # bcrypt has a 72-byte limit on passwords; truncate if needed
        if isinstance(password, str):
            password_bytes = password.encode("utf-8")
            if len(password_bytes) > 72:
                password = password_bytes[:72].decode("utf-8", errors="ignore")

        user = User(
            email=email,
            password_hash=bcrypt.hash(password),
            display_name=display_name,
            role=role,
            auth_provider="local",
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        result = await self.session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            raise AuthError("Invalid email or password")

        if user.auth_provider != "local":
            raise AuthError(f"User uses {user.auth_provider} authentication")

        if not user.password_hash or not bcrypt.verify(password, user.password_hash):
            raise AuthError("Invalid email or password")

        if not user.is_active:
            raise AuthError("Account is inactive")

        return user

    async def create_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(
            data={"sub": str(user.id), "role": user.role},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        refresh_token_str = create_refresh_token()

        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        # Store refresh token
        from hashlib import sha256
        rt = RefreshToken(
            user_id=user.id,
            token_hash=sha256(refresh_token_str.encode()).hexdigest(),
            expires_at=expires_at,
        )
        self.session.add(rt)
        await self.session.flush()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token_str,
            user=UserResponse.model_validate(user),
        )

    async def refresh_tokens(self, refresh_token_str: str) -> TokenResponse:
        from hashlib import sha256

        token_hash = sha256(refresh_token_str.encode()).hexdigest()
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked == False,
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
        )
        rt = result.scalar_one_or_none()
        if not rt:
            raise AuthError("Invalid or expired refresh token")

        # Revoke old token
        rt.revoked = True

        # Get user
        result = await self.session.execute(select(User).where(User.id == rt.user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise AuthError("User not found or inactive")

        return await self.create_tokens(user)

    async def revoke_refresh_token(self, refresh_token_str: str):
        from hashlib import sha256

        token_hash = sha256(refresh_token_str.encode()).hexdigest()
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        rt = result.scalar_one_or_none()
        if rt:
            rt.revoked = True
            await self.session.flush()

    async def update_user(self, user_id: uuid.UUID, update_data) -> User:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise AuthError("User not found")

        if update_data.display_name is not None:
            user.display_name = update_data.display_name
        if update_data.avatar_url is not None:
            user.avatar_url = update_data.avatar_url

        await self.session.flush()
        return user

    async def change_password(self, user_id: uuid.UUID, old_password: str, new_password: str):
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise AuthError("User not found")

        if not user.password_hash or not bcrypt.verify(old_password, user.password_hash):
            raise AuthError("Current password is incorrect")

        user.password_hash = bcrypt.hash(new_password)
        await self.session.flush()
