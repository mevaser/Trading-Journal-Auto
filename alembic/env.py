"""Alembic environment - async engine (SQLite / Postgres)."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig
from pathlib import Path
from types import ModuleType
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import importlib
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))  # allows `import app.*`

from app.core.config import get_database_url

# Canonical DB URL for both runtime and migrations.
config.set_main_option("sqlalchemy.url", get_database_url())

models: ModuleType = importlib.import_module("app.db.models")  # noqa: F401
target_metadata = models.Base.metadata  # type: ignore[attr-defined]


def run_migrations_offline() -> None:
    """Generate SQL scripts without DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Any) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations using AsyncEngine."""
    connectable: AsyncEngine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.begin() as conn:
        await conn.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
