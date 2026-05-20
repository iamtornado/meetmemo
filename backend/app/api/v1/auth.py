from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.errors import AuthError, ConflictError
from app.models.user import User
from app.schemas.user import (
    ChangePassword,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    RefreshTokenRequest,
    UserUpdate,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(body: UserCreate, session: AsyncSession = Depends(get_session)):
    auth_service = AuthService(session)
    # First user becomes admin
    result = await session.execute(select(func.count()).select_from(User))
    user_count = result.scalar()
    role = "admin" if user_count == 0 else "member"

    user = await auth_service.register(
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        role=role,
    )
    tokens = await auth_service.create_tokens(user)
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, session: AsyncSession = Depends(get_session)):
    auth_service = AuthService(session)

    # First check if this is an AD user
    from app.auth.ldap_provider import ldap_provider
    if ldap_provider.enabled:
        # Try LDAP authentication first (AD users auto-create local account)
        try:
            user = await auth_service.authenticate_ldap(body.email, body.password)
            tokens = await auth_service.create_tokens(user)
            return tokens
        except AuthError:
            # LDAP failed, fall through to local auth
            pass

    # Fall back to local authentication
    user = await auth_service.authenticate(body.email, body.password)
    tokens = await auth_service.create_tokens(user)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshTokenRequest, session: AsyncSession = Depends(get_session)):
    auth_service = AuthService(session)
    tokens = await auth_service.refresh_tokens(body.refresh_token)
    return tokens


@router.post("/logout")
async def logout(
    body: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    auth_service = AuthService(session)
    await auth_service.revoke_refresh_token(body.refresh_token)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    auth_service = AuthService(session)
    return await auth_service.update_user(user.id, body)


@router.post("/change-password")
async def change_password(
    body: ChangePassword,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    auth_service = AuthService(session)
    await auth_service.change_password(user.id, body.old_password, body.new_password)
    return {"message": "Password changed"}


@router.get("/providers")
async def get_auth_providers():
    from app.auth.ldap_provider import ldap_provider
    from app.auth.oidc_provider import oidc_provider
    providers = ["local"]
    if ldap_provider.enabled:
        providers.append("ldap")
    if oidc_provider.enabled:
        providers.append("oidc")
    return {"providers": providers}
