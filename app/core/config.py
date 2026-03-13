from __future__ import annotations

import os


DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/trades.db"


def get_database_url() -> str:
    """Return database URL from environment or default local SQLite path."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
