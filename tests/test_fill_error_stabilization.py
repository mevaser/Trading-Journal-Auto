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
    monkeypatch.setenv("APP_SECRET_KEY", "fill-stabilization-secret")
    clear_settings_cache()

    db_path = (tmp_path / "fill_stabilization.db").resolve()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_local() as session:
        tenant = Tenant(id=1, slug="default", name="Default", is_active=True)
        user = User(username="fills", email="fills@example.com", password_hash="x")
        session.add_all([tenant, user])
        await session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner", is_active=True))
        await session.commit()

    token_pair = issue_token_pair(
        user_id=1,
        tenant_id=1,
        roles=["owner"],
        secret_key="fill-stabilization-secret",
    )
    headers = {"Authorization": f"Bearer {token_pair.access_token}", "X-Tenant-ID": "1"}

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, headers

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()


async def _create_trade(client: AsyncClient, headers: dict[str, str]) -> int:
    response = await client.post(
        "/trades/",
        json={"symbol": "AAPL", "direction": "LONG", "user_id": 1},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def _assert_request_id(payload: dict, expected: str) -> None:
    assert payload["request_id"] == expected
    assert payload["error"]["request_id"] == expected


@pytest.mark.anyio
async def test_fill_negative_quantity_fails_request_validation(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers)

    response = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": "2026-03-18T12:00:00Z",
            "side": "BUY",
            "quantity": "-1",
            "price": "100",
            "commission": "0",
            "source": "manual",
        },
        headers={**headers, "X-Request-ID": "req-fill-negative-quantity"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "request_validation"
    _assert_request_id(payload, "req-fill-negative-quantity")


@pytest.mark.anyio
async def test_fill_zero_price_fails_request_validation(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers)

    response = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": "2026-03-18T12:00:00Z",
            "side": "BUY",
            "quantity": "1",
            "price": "0",
            "commission": "0",
            "source": "manual",
        },
        headers={**headers, "X-Request-ID": "req-fill-zero-price"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "request_validation"
    _assert_request_id(payload, "req-fill-zero-price")


@pytest.mark.anyio
async def test_duplicate_external_fill_id_maps_to_domain_validation(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers)
    fill_payload = {
        "fill_datetime": "2026-03-18T12:00:00Z",
        "side": "BUY",
        "quantity": "1",
        "price": "100",
        "commission": "0",
        "source": "manual",
        "external_fill_id": "dup-1",
    }

    first = await client.post(f"/trades/{trade_id}/fills", json=fill_payload, headers=headers)
    assert first.status_code == 201

    duplicate = await client.post(
        f"/trades/{trade_id}/fills",
        json=fill_payload,
        headers={**headers, "X-Request-ID": "req-fill-duplicate"},
    )

    assert duplicate.status_code == 400
    payload = duplicate.json()
    assert payload["error"]["code"] == "domain_validation"
    assert payload["error"]["message"] == "external_fill_id already exists for this tenant and source"
    _assert_request_id(payload, "req-fill-duplicate")


@pytest.mark.anyio
async def test_domain_error_always_includes_non_null_request_id(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers)
    fill_payload = {
        "fill_datetime": "2026-03-18T12:00:00Z",
        "side": "BUY",
        "quantity": "1",
        "price": "100",
        "commission": "0",
        "source": "manual",
        "external_fill_id": "dup-2",
    }

    first = await client.post(f"/trades/{trade_id}/fills", json=fill_payload, headers=headers)
    assert first.status_code == 201

    duplicate = await client.post(f"/trades/{trade_id}/fills", json=fill_payload, headers=headers)
    assert duplicate.status_code == 400

    payload = duplicate.json()
    assert payload["error"]["code"] == "domain_validation"
    assert payload["request_id"]
    assert payload["error"]["request_id"]
