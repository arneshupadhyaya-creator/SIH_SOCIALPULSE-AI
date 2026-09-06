"""
Async and sync SQLAlchemy engine + session factories.

* **Async** engine/session — used by FastAPI request handlers and ingestion.
* **Sync** engine — used by Alembic migrations (which don't support async).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings

_settings = get_settings()

# ── Async (app runtime) ──────────────────────────────────────
async_engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency-injectable async session context manager."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Sync (Alembic only) ──────────────────────────────────────
sync_engine = create_engine(
    _settings.sync_database_url,
    echo=False,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(bind=sync_engine)


def get_sync_session() -> Session:
    """Return a plain sync session (for Alembic and one-off scripts)."""
    return SyncSessionLocal()
