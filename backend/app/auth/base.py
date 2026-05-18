from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.user import User


class AuthProvider(ABC):
    """Abstract base class for authentication providers."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        ...

    @abstractmethod
    async def authenticate(self, identifier: str, password: str) -> User | None:
        ...

    @abstractmethod
    async def get_user_info(self, identifier: str) -> dict | None:
        ...

    @abstractmethod
    async def get_user_groups(self, identifier: str) -> list[str]:
        ...
