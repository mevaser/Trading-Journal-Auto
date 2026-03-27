from __future__ import annotations

import os
import sys
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import DEFAULT_DATABASE_URL, get_database_url


def _can_use_asyncpg() -> bool:
    try:
        import asyncpg  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def _resolve_database_url() -> str:
    database_url = get_database_url()
    if database_url.startswith("postgresql+asyncpg://") and not _can_use_asyncpg():
        if os.getenv("PYTEST_CURRENT_TEST") or "pytest" in " ".join(sys.argv).lower():
            return DEFAULT_DATABASE_URL
    return database_url


DATABASE_URL = _resolve_database_url()
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
