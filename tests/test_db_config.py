from app.core.config import DEFAULT_DATABASE_URL, get_database_url


def test_database_url_default(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == DEFAULT_DATABASE_URL


def test_database_url_env_override(monkeypatch) -> None:
    custom_url = "sqlite+aiosqlite:///./data/custom.db"
    monkeypatch.setenv("DATABASE_URL", custom_url)
    assert get_database_url() == custom_url
