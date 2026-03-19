import pytest

import app.core.config as config_module
from app.core.config import (
    DEFAULT_DATABASE_URL,
    clear_settings_cache,
    get_database_url,
    get_settings,
)


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _ignore_repo_env_files(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "_env_file_order", lambda profile: tuple())


def test_database_url_default_dev_profile(monkeypatch) -> None:
    _ignore_repo_env_files(monkeypatch)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    assert get_settings().profile == "dev"
    assert get_database_url() == DEFAULT_DATABASE_URL


def test_database_url_env_override(monkeypatch) -> None:
    custom_url = "sqlite+aiosqlite:///./data/custom.db"
    monkeypatch.setenv("DATABASE_URL", custom_url)
    monkeypatch.setenv("APP_SECRET_KEY", "unit-test-secret")
    assert get_database_url() == custom_url


def test_stage_profile_has_deterministic_default(monkeypatch) -> None:
    _ignore_repo_env_files(monkeypatch)
    monkeypatch.setenv("APP_ENV", "stage")
    monkeypatch.setenv("APP_SECRET_KEY", "stage-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = get_settings()

    assert settings.profile == "stage"
    assert settings.database_url == "sqlite+aiosqlite:///./data/trades_stage.db"
    assert settings.app_debug is False


def test_invalid_profile_raises(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "qa")
    monkeypatch.setenv("APP_SECRET_KEY", "secret")

    with pytest.raises(ValueError, match="Invalid APP_ENV"):
        get_settings()


def test_stage_and_prod_require_secret(monkeypatch) -> None:
    _ignore_repo_env_files(monkeypatch)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)

    with pytest.raises(ValueError, match="APP_SECRET_KEY is required"):
        get_settings()
