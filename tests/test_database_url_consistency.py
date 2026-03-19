from __future__ import annotations

import importlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.core.config import clear_settings_cache, get_database_url


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_runtime_and_alembic_use_same_database_url(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "shared_phase1.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["APP_SECRET_KEY"] = "test-secret"

    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert db_path.exists()
    assert get_database_url() == database_url

    import app.db.session as session_module

    importlib.reload(session_module)
    runtime_url = str(session_module.engine.url)
    assert make_url(runtime_url).database == make_url(database_url).database

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "alembic_version" in tables
