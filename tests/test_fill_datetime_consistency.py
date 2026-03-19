from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.tokens import issue_token_pair
from app.core.config import clear_settings_cache
from app.db.models import Base, Membership, Tenant, User
from app.db.session import get_db
from app.main import app


def _parse_iso_utc(value: str):
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    return __import__("datetime").datetime.fromisoformat(value)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def api_client_with_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    clear_settings_cache()

    db_path = (tmp_path / "fill_datetime_consistency.db").resolve()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_local() as session:
        tenant = Tenant(id=1, slug="default", name="Default", is_active=True)
        user = User(username="dt_user", email="dt@example.com", password_hash="x")
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
    headers = {"Authorization": f"Bearer {token_pair.access_token}", "X-Tenant-ID": "1"}

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_path, headers

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()


async def _create_trade(client: AsyncClient, headers: dict[str, str]) -> int:
    resp = await client.post(
        "/trades/",
        json={"symbol": "AAPL", "direction": "LONG", "user_id": 1},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.anyio
async def test_naive_fill_datetime_is_normalized_to_utc(api_client_with_db) -> None:
    client, _, headers = api_client_with_db
    trade_id = await _create_trade(client, headers)

    resp = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": "2026-03-09T10:00:00",
            "side": "BUY",
            "quantity": "1",
            "price": "100",
            "commission": "0",
            "source": "manual",
        },
        headers=headers,
    )
    assert resp.status_code == 201

    dt = _parse_iso_utc(resp.json()["fill_datetime"])
    assert dt.utcoffset() == timedelta(0)


@pytest.mark.anyio
async def test_aware_fill_datetime_is_converted_to_utc(api_client_with_db) -> None:
    client, _, headers = api_client_with_db
    trade_id = await _create_trade(client, headers)

    resp = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": "2026-03-09T12:00:00+02:00",
            "side": "BUY",
            "quantity": "1",
            "price": "100",
            "commission": "0",
            "source": "manual",
        },
        headers=headers,
    )
    assert resp.status_code == 201

    dt = _parse_iso_utc(resp.json()["fill_datetime"])
    assert dt.utcoffset() == timedelta(0)
    assert dt.hour == 10


@pytest.mark.anyio
async def test_mixed_existing_fills_do_not_break_sorting(api_client_with_db) -> None:
    client, db_path, headers = api_client_with_db
    trade_id = await _create_trade(client, headers)

    # Simulate legacy row that was stored as naive datetime text.
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trade_fills (trade_id, tenant_id, fill_datetime, side, quantity, price, commission, source)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (trade_id, "2026-03-09 09:30:00", "BUY", "1", "100", "0", "manual"),
        )
        conn.commit()

    aware_resp = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": "2026-03-09T12:00:00+02:00",
            "side": "BUY",
            "quantity": "1",
            "price": "100",
            "commission": "0",
            "source": "manual",
        },
        headers=headers,
    )
    assert aware_resp.status_code == 201

    naive_resp = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": "2026-03-09T08:00:00",
            "side": "BUY",
            "quantity": "1",
            "price": "100",
            "commission": "0",
            "source": "manual",
        },
        headers=headers,
    )
    assert naive_resp.status_code == 201

    fills_resp = await client.get(f"/trades/{trade_id}/fills", headers=headers)
    assert fills_resp.status_code == 200

    ordered = [_parse_iso_utc(item["fill_datetime"]) for item in fills_resp.json()]
    assert ordered == sorted(ordered)
    assert all(item.utcoffset() == timedelta(0) for item in ordered)
