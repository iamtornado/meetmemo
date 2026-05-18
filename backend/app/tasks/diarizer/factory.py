from __future__ import annotations

import logging
from typing import Literal

from app.config import settings
from app.tasks.diarizer.base import BaseDiarizer

logger = logging.getLogger(__name__)

DiarizeProvider = Literal["local", "remote"]

# Module-level singleton cache
_diarizer_instance: BaseDiarizer | None = None


def get_diarizer() -> BaseDiarizer:
    """Factory function — returns a singleton diarizer based on DIARIZE_PROVIDER.

    The provider is resolved at first call (lazy) and cached for the lifetime
    of the worker process.
    """
    global _diarizer_instance

    if _diarizer_instance is not None:
        return _diarizer_instance

    provider: DiarizeProvider = settings.DIARIZE_PROVIDER

    logger.info(f"Initializing diarizer provider: {provider}")

    if provider == "local":
        from app.tasks.diarizer.local import LocalDiarizer
        _diarizer_instance = LocalDiarizer()
    elif provider == "remote":
        from app.tasks.diarizer.remote import RemoteDiarizer
        _diarizer_instance = RemoteDiarizer()
    else:
        raise ValueError(
            f"Unknown DIARIZE_PROVIDER: {provider!r}. "
            f"Expected one of: {get_available_providers()}"
        )

    logger.info(f"Diarizer provider initialized: {type(_diarizer_instance).__name__}")
    return _diarizer_instance


def get_available_providers() -> list[DiarizeProvider]:
    return ["local", "remote"]


def reset_diarizer() -> None:
    """Reset the cached diarizer instance (useful for tests / config reload)."""
    global _diarizer_instance
    _diarizer_instance = None
    logger.debug("Diarizer instance reset")
