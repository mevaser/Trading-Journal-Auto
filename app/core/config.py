from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from typing import Final

from dotenv import dotenv_values


DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/trades.db"
DEFAULT_PROFILE: Final[str] = "dev"
PROFILE_ENV_VAR: Final[str] = "APP_ENV"
_VALID_PROFILES: Final[set[str]] = {"dev", "stage", "prod"}

_PROFILE_DEFAULTS: Final[dict[str, dict[str, str]]] = {
    "dev": {
        "DATABASE_URL": "sqlite+aiosqlite:///./data/trades.db",
        "APP_DEBUG": "true",
    },
    "stage": {
        "DATABASE_URL": "sqlite+aiosqlite:///./data/trades_stage.db",
        "APP_DEBUG": "false",
    },
    "prod": {
        "DATABASE_URL": "sqlite+aiosqlite:///./data/trades_prod.db",
        "APP_DEBUG": "false",
    },
}


@dataclass(frozen=True)
class AppSettings:
    profile: str
    database_url: str
    app_debug: bool
    app_secret_key: str
    access_token_expire_minutes: int


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    profile = _resolve_profile()
    merged = _resolve_env(profile)
    database_url = merged.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    app_debug = _parse_bool(merged.get("APP_DEBUG", "false"))
    app_secret_key = _resolve_secret_key(profile, merged.get("APP_SECRET_KEY"))
    access_token_expire_minutes = _parse_positive_int(
        merged.get("ACCESS_TOKEN_EXPIRE_MINUTES"),
        default=15,
        key_name="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    return AppSettings(
        profile=profile,
        database_url=database_url,
        app_debug=app_debug,
        app_secret_key=app_secret_key,
        access_token_expire_minutes=access_token_expire_minutes,
    )


def get_database_url() -> str:
    """Return canonical database URL resolved from the active settings profile."""
    return get_settings().database_url


def clear_settings_cache() -> None:
    """Clear memoized settings; useful for tests that mutate environment variables."""
    get_settings.cache_clear()


def _resolve_profile() -> str:
    raw_profile = os.getenv(PROFILE_ENV_VAR, DEFAULT_PROFILE).strip().lower()
    if raw_profile not in _VALID_PROFILES:
        valid = ", ".join(sorted(_VALID_PROFILES))
        raise ValueError(f"Invalid {PROFILE_ENV_VAR}='{raw_profile}'. Expected one of: {valid}")
    return raw_profile


def _resolve_env(profile: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    merged.update(_PROFILE_DEFAULTS[profile])
    for env_file in _env_file_order(profile):
        if env_file.exists():
            file_values = dotenv_values(env_file)
            merged.update({k: v for k, v in file_values.items() if v is not None})
    merged.update(os.environ)
    return merged


def _env_file_order(profile: str) -> tuple[Path, ...]:
    root = _project_root()
    return (
        root / ".env",
        root / f".env.{profile}",
        root / ".env.local",
        root / f".env.{profile}.local",
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_secret_key(profile: str, secret: str | None) -> str:
    if secret:
        return secret
    if profile == "dev":
        return "dev-insecure-change-me"
    raise ValueError(
        "APP_SECRET_KEY is required for stage/prod profiles. "
        "Set it through environment variables or .env profile files."
    )


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_positive_int(raw: str | None, *, default: int, key_name: str) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{key_name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{key_name} must be > 0")
    return value
