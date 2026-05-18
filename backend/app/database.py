from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine for Celery tasks (avoids async loop conflicts in worker processes)
sync_database_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
sync_engine = create_engine(
    sync_database_url,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=10,
)
sync_session_factory = sessionmaker(
    sync_engine,
    class_=Session,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:  # type: ignore
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
