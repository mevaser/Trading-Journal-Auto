from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_migration_adds_duration_days_column(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "migration_duration_days.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(trades)")]
        current_revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert "duration_days" in columns
    assert current_revision == "f2a6c4b9e1d7"
