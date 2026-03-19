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
    monkeypatch.setenv("APP_SECRET_KEY", "dep-test-secret")
    clear_settings_cache()

    db_file = (tmp_path / "auth_dependency.db").resolve()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_local() as session:
        tenant1 = Tenant(id=1, slug="default", name="Default", is_active=True)
        tenant2 = Tenant(id=2, slug="desk-2", name="Desk 2", is_active=True)
        active_user = User(username="active", email="active@example.com", password_hash="x")
        inactive_user = User(username="nomember", email="nomember@example.com", password_hash="x")

        session.add_all([tenant1, tenant2, active_user, inactive_user])
        await session.flush()

        session.add(Membership(tenant_id=1, user_id=active_user.id, role="owner", is_active=True))
        await session.commit()

    async def override_get_db():
        async with session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()


def _auth_headers(*, user_id: int, tenant_id: int, roles: list[str] | tuple[str, ...], tenant_header: int | None = None):
    pair = issue_token_pair(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=list(roles),
        secret_key="dep-test-secret",
    )
    headers = {"Authorization": f"Bearer {pair.access_token}"}
    if tenant_header is not None:
        headers["X-Tenant-ID"] = str(tenant_header)
    return headers


@pytest.mark.anyio
async def test_valid_token_and_membership_allows_access(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/trades/",
        headers=_auth_headers(user_id=1, tenant_id=1, roles=["owner"], tenant_header=1),
    )

    assert response.status_code == 200


@pytest.mark.anyio
async def test_invalid_token_is_rejected(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/trades/",
        headers={"Authorization": "Bearer not-a-real-token", "X-Tenant-ID": "1"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "auth_unauthorized"
    assert payload["error"]["message"] == "Invalid access token"


@pytest.mark.anyio
async def test_missing_membership_is_rejected(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/trades/",
        headers=_auth_headers(user_id=2, tenant_id=1, roles=["owner"], tenant_header=1),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "auth_forbidden"
    assert payload["error"]["message"] == "Tenant membership is missing or inactive"


@pytest.mark.anyio
async def test_tenant_mismatch_header_vs_token_is_rejected(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/trades/",
        headers=_auth_headers(user_id=1, tenant_id=1, roles=["owner"], tenant_header=2),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "auth_forbidden"
    assert payload["error"]["message"] == "Tenant header does not match token tenant"
