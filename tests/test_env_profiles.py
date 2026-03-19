from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import clear_settings_cache, get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_profile_env_file_overrides_defaults(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    profile_file = repo_root / ".env.stage"

    monkeypatch.setenv("APP_ENV", "stage")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)

    profile_file.write_text(
        "DATABASE_URL=sqlite+aiosqlite:///./data/from_stage_env_file.db\n"
        "APP_SECRET_KEY=stage-file-secret\n",
        encoding="utf-8",
    )

    try:
        settings = get_settings()
        assert settings.database_url == "sqlite+aiosqlite:///./data/from_stage_env_file.db"
        assert settings.app_secret_key == "stage-file-secret"
    finally:
        profile_file.unlink(missing_ok=True)


def test_process_env_overrides_profile_env_file(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    profile_file = repo_root / ".env.prod"

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("APP_SECRET_KEY", "process-secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/from_process_env.db")

    profile_file.write_text(
        "DATABASE_URL=sqlite+aiosqlite:///./data/from_prod_env_file.db\n"
        "APP_SECRET_KEY=file-secret\n",
        encoding="utf-8",
    )

    try:
        settings = get_settings()
        assert settings.database_url == "sqlite+aiosqlite:///./data/from_process_env.db"
        assert settings.app_secret_key == "process-secret"
    finally:
        profile_file.unlink(missing_ok=True)

