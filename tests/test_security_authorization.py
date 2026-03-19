from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.tokens import issue_token_pair
from app.core.config import clear_settings_cache
from app.db.models import Base, Membership, Tenant, Trade, User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def security_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "security-test-secret")
    clear_settings_cache()

    db_path = (tmp_path / "security_authz.db").resolve()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_local() as session:
        tenant1 = Tenant(id=1, slug="default", name="Default", is_active=True)
        tenant2 = Tenant(id=2, slug="desk-2", name="Desk 2", is_active=True)

        owner_t1 = User(username="owner_t1", email="owner_t1@example.com", password_hash="x")
        owner_t2 = User(username="owner_t2", email="owner_t2@example.com", password_hash="x")
        member_t1 = User(username="member_t1", email="member_t1@example.com", password_hash="x")
        no_membership = User(username="no_membership", email="no_membership@example.com", password_hash="x")

        session.add_all([tenant1, tenant2, owner_t1, owner_t2, member_t1, no_membership])
        await session.flush()

        session.add_all(
            [
                Membership(tenant_id=1, user_id=owner_t1.id, role="owner", is_active=True),
                Membership(tenant_id=2, user_id=owner_t2.id, role="owner", is_active=True),
                Membership(tenant_id=1, user_id=member_t1.id, role="member", is_active=True),
            ]
        )

        session.add_all(
            [
                Trade(tenant_id=1, user_id=owner_t1.id, symbol="AAPL", direction="LONG", status="open"),
                Trade(tenant_id=2, user_id=owner_t2.id, symbol="MSFT", direction="LONG", status="open"),
            ]
        )
        await session.commit()

    async with session_local() as session:
        users = (await session.execute(select(User.id, User.username))).all()
        ids = {username: user_id for user_id, username in users}
        trades = (await session.execute(select(Trade.id, Trade.symbol, Trade.tenant_id))).all()
        ids["trade_t1"] = next(trade_id for trade_id, _, tenant_id in trades if tenant_id == 1)
        ids["trade_t2"] = next(trade_id for trade_id, _, tenant_id in trades if tenant_id == 2)

    async def override_get_db():
        async with session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_path, ids

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()


def _headers(*, user_id: int, tenant_id: int, roles: list[str], tenant_header: int | None = None) -> dict[str, str]:
    pair = issue_token_pair(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        secret_key="security-test-secret",
    )
    headers = {"Authorization": f"Bearer {pair.access_token}"}
    if tenant_header is not None:
        headers["X-Tenant-ID"] = str(tenant_header)
    return headers


def _assert_error_envelope(payload: dict, *, code: str) -> None:
    assert "error" in payload
    assert payload["error"]["code"] == code
    assert "message" in payload["error"]
    assert "request_id" in payload["error"]
    assert "retryable" in payload["error"]
    assert "request_id" in payload


@pytest.mark.anyio
async def test_missing_token_denied_with_normalized_error(security_client) -> None:
    client, _, _ = security_client

    response = await client.get("/trades/")

    assert response.status_code == 401
    _assert_error_envelope(response.json(), code="auth_unauthorized")


@pytest.mark.anyio
async def test_invalid_token_denied_with_normalized_error(security_client) -> None:
    client, _, _ = security_client

    response = await client.get(
        "/trades/",
        headers={"Authorization": "Bearer invalid-token", "X-Tenant-ID": "1"},
    )

    assert response.status_code == 401
    _assert_error_envelope(response.json(), code="auth_unauthorized")


@pytest.mark.anyio
async def test_cross_tenant_read_denied_on_tenant_header_mismatch(security_client) -> None:
    client, _, ids = security_client

    response = await client.get(
        "/trades/",
        headers=_headers(user_id=ids["owner_t1"], tenant_id=1, roles=["owner"], tenant_header=2),
    )

    assert response.status_code == 403
    _assert_error_envelope(response.json(), code="auth_forbidden")


@pytest.mark.anyio
async def test_cross_tenant_write_denied_and_no_write_occurs(security_client) -> None:
    client, db_path, ids = security_client

    with sqlite3.connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

    response = await client.post(
        "/trades/",
        json={"symbol": "TSLA", "direction": "LONG", "user_id": ids["owner_t1"]},
        headers=_headers(user_id=ids["owner_t1"], tenant_id=1, roles=["owner"], tenant_header=2),
    )

    with sqlite3.connect(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

    assert response.status_code == 403
    _assert_error_envelope(response.json(), code="auth_forbidden")
    assert after_count == before_count


@pytest.mark.anyio
async def test_missing_membership_denied(security_client) -> None:
    client, _, ids = security_client

    response = await client.get(
        "/trades/",
        headers=_headers(user_id=ids["no_membership"], tenant_id=1, roles=["owner"], tenant_header=1),
    )

    assert response.status_code == 403
    _assert_error_envelope(response.json(), code="auth_forbidden")


@pytest.mark.anyio
async def test_role_claim_mismatch_denied(security_client) -> None:
    client, _, ids = security_client

    # User has tenant membership role=member, token claims role=owner.
    response = await client.get(
        "/trades/",
        headers=_headers(user_id=ids["member_t1"], tenant_id=1, roles=["owner"], tenant_header=1),
    )

    assert response.status_code == 403
    _assert_error_envelope(response.json(), code="auth_forbidden")


@pytest.mark.anyio
async def test_owner_and_member_roles_can_access_when_claims_match_membership(security_client) -> None:
    client, _, ids = security_client

    owner_resp = await client.get(
        "/trades/",
        headers=_headers(user_id=ids["owner_t1"], tenant_id=1, roles=["owner"], tenant_header=1),
    )
    member_resp = await client.get(
        "/trades/",
        headers=_headers(user_id=ids["member_t1"], tenant_id=1, roles=["member"], tenant_header=1),
    )

    assert owner_resp.status_code == 200
    assert member_resp.status_code == 200


@pytest.mark.anyio
async def test_trade_list_is_filtered_to_token_tenant(security_client) -> None:
    client, _, ids = security_client

    response = await client.get(
        "/trades/",
        headers=_headers(user_id=ids["owner_t1"], tenant_id=1, roles=["owner"], tenant_header=1),
    )

    assert response.status_code == 200
    symbols = {item["symbol"] for item in response.json()}
    assert "AAPL" in symbols
    assert "MSFT" not in symbols


@pytest.mark.anyio
async def test_cross_tenant_trade_id_read_denied(security_client) -> None:
    client, _, ids = security_client

    response = await client.get(
        f"/trades/{ids['trade_t2']}",
        headers=_headers(user_id=ids["owner_t1"], tenant_id=1, roles=["owner"], tenant_header=1),
    )

    assert response.status_code == 404
    _assert_error_envelope(response.json(), code="resource_not_found")


@pytest.mark.anyio
async def test_cross_tenant_trade_id_write_denied_for_fills(security_client) -> None:
    client, _, ids = security_client

    response = await client.post(
        f"/trades/{ids['trade_t2']}/fills",
        json={
            "fill_datetime": "2026-03-18T12:00:00Z",
            "side": "BUY",
            "quantity": "1",
            "price": "10",
            "commission": "0",
            "source": "manual",
        },
        headers=_headers(user_id=ids["owner_t1"], tenant_id=1, roles=["owner"], tenant_header=1),
    )

    assert response.status_code == 404
    _assert_error_envelope(response.json(), code="resource_not_found")
