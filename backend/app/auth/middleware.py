from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from jose import JWTError, jwt

from app.config import settings


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


def create_refresh_token() -> str:
    return str(uuid.uuid4()) + "-" + str(uuid.uuid4())


def hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()
