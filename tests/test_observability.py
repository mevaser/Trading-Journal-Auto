from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.tokens import issue_token_pair
from app.core.config import clear_settings_cache
from app.db.models import Base, Membership, Tenant, User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def api_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    clear_settings_cache()

    db_file = tmp_path / "test_observability.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_local() as session:
        tenant = Tenant(id=1, slug="default", name="Default", is_active=True)
        user = User(username="obs", email="obs@example.com", password_hash="x")
        session.add_all([tenant, user])
        await session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner", is_active=True))
        await session.commit()

    token_pair = issue_token_pair(
        user_id=1,
        tenant_id=1,
        roles=["owner"],
        secret_key="test-secret",
    )
    auth_headers = {"Authorization": f"Bearer {token_pair.access_token}", "X-Tenant-ID": "1"}

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, auth_headers

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()


@pytest.mark.anyio
async def test_request_id_header_is_echoed(api_client) -> None:
    client, _ = api_client
    response = await client.get("/", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"


@pytest.mark.anyio
async def test_not_found_error_uses_taxonomy_and_request_id(api_client) -> None:
    client, auth_headers = api_client
    response = await client.get(
        "/trades/999",
        headers={**auth_headers, "X-Request-ID": "req-not-found"},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "resource_not_found"
    assert payload["error"]["message"] == "Trade not found"
    assert payload["request_id"] == "req-not-found"
    assert payload["error"]["request_id"] == "req-not-found"


@pytest.mark.anyio
async def test_request_validation_error_uses_taxonomy(api_client) -> None:
    client, auth_headers = api_client
    response = await client.post("/trades/", json={"symbol": "AAPL"}, headers=auth_headers)

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "request_validation"
    assert payload["error"]["message"] == "Request validation failed"
    assert isinstance(payload["error"]["details"], list)
    assert payload["error"]["retryable"] is False
    assert "request_id" in payload
