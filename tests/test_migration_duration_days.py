from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from tests.utils.alembic_helpers import get_head_revision


def _run_alembic(repo_root: Path, env: dict[str, str], *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_adds_duration_days_column(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "migration_duration_days.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(trades)")]
        current_revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert "duration_days" in columns
    assert current_revision == get_head_revision()


def test_migration_downgrade_handles_nullable_trade_fields(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "migration_nullable_fields.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            ("migration-user", "migration@example.com", "x"),
        )
        user_id = conn.execute("SELECT id FROM users WHERE email = ?", ("migration@example.com",)).fetchone()[0]
        conn.execute(
            """
            INSERT INTO trades (
                user_id, symbol, entry_date, entry_price, quantity, direction,
                status, opened_at, created_at, updated_at
            ) VALUES (?, ?, NULL, NULL, NULL, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (user_id, "AAPL", "LONG", "open"),
        )
        conn.commit()

    _run_alembic(repo_root, env, "downgrade", "base")
    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(trades)")]

    assert "duration_days" in columns
