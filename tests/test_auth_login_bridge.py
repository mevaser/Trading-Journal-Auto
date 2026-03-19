from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.passwords import hash_password
from app.auth.tokens import decode_access_token
from app.core.config import clear_settings_cache
from app.db.models import Base, Membership, Tenant, Trade, User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def login_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "login-bridge-secret")
    monkeypatch.setenv("AUTH_BRIDGE_BOOTSTRAP_ENABLED", "false")
    clear_settings_cache()

    db_path = (tmp_path / "auth_login_bridge.db").resolve()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_local() as session:
        tenant = Tenant(id=1, slug="default", name="Default", is_active=True)
        user = User(username="manual", email="manual@example.com", password_hash=hash_password("manual-pass"))
        session.add_all([tenant, user])
        await session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner", is_active=True))
        session.add(Trade(tenant_id=tenant.id, user_id=user.id, symbol="AAPL", direction="LONG", status="open"))
        await session.commit()

    async def override_get_db():
        async with session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_local

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()


@pytest.mark.anyio
async def test_login_returns_real_access_token_and_allows_trades_access(login_client) -> None:
    client, _ = login_client

    login_resp = await client.post(
        "/auth/login",
        json={"email": "manual@example.com", "password": "manual-pass"},
    )
    assert login_resp.status_code == 200
    payload = login_resp.json()

    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["tenant_id"] == 1
    assert payload["roles"] == ["owner"]
    assert payload["session_id"]

    claims = decode_access_token(payload["access_token"], secret_key="login-bridge-secret")
    assert claims.sub > 0
    assert claims.tenant_id == 1
    assert claims.roles == ("owner",)

    trades_resp = await client.get(
        "/trades/",
        headers={
            "Authorization": f"Bearer {payload['access_token']}",
            "X-Tenant-ID": str(payload["tenant_id"]),
        },
    )
    assert trades_resp.status_code == 200
    assert len(trades_resp.json()) == 1


@pytest.mark.anyio
async def test_login_invalid_credentials_returns_401(login_client) -> None:
    client, _ = login_client

    response = await client.post(
        "/auth/login",
        json={"email": "manual@example.com", "password": "wrong-pass"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_unauthorized"


@pytest.mark.anyio
async def test_login_bootstrap_path_creates_deterministic_test_user(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "login-bridge-secret")
    monkeypatch.setenv("AUTH_BRIDGE_BOOTSTRAP_ENABLED", "true")
    monkeypatch.setenv("AUTH_BRIDGE_BOOTSTRAP_EMAIL", "bridge@example.com")
    monkeypatch.setenv("AUTH_BRIDGE_BOOTSTRAP_PASSWORD", "bridge-password-change-me")
    monkeypatch.setenv("AUTH_BRIDGE_BOOTSTRAP_TENANT_ID", "1")
    clear_settings_cache()

    db_path = (tmp_path / "auth_login_bootstrap.db").resolve()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_resp = await client.post(
            "/auth/login",
            json={"email": "bridge@example.com", "password": "bridge-password-change-me"},
        )
        assert login_resp.status_code == 200

    async with session_local() as session:
        user = (await session.execute(select(User).where(User.email == "bridge@example.com"))).scalar_one_or_none()
        membership = (
            await session.execute(
                select(Membership).where(and_(Membership.user_id == user.id, Membership.tenant_id == 1))
            )
        ).scalar_one_or_none()

    assert user is not None
    assert membership is not None

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()
