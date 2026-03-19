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


CANONICAL_TRADE_KEYS = {
    "id",
    "user_id",
    "symbol",
    "direction",
    "asset_type",
    "strategy",
    "thesis",
    "reason_entry",
    "reason_exit",
    "notes",
    "tags",
    "status",
    "opened_at",
    "closed_at",
    "avg_entry_price",
    "avg_exit_price",
    "quantity_opened",
    "quantity_closed",
    "remaining_quantity",
    "pnl_usd",
    "pnl_pct",
    "is_intraday",
    "duration_days",
    "created_at",
    "updated_at",
    "fills",
}

LEGACY_KEYS = {
    "entry_date",
    "entry_price",
    "quantity",
    "exit_date",
    "exit_price",
    "portfolio_pct",
    "estimates",
    "stop_loss",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def api_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    clear_settings_cache()

    db_file = tmp_path / "test_phase1_contract.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_local() as session:
        tenant = Tenant(id=1, slug="default", name="Default", is_active=True)
        user = User(username="phase1", email="phase1@example.com", password_hash="x")
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
async def test_trade_contract_in_list_and_detail(api_client) -> None:
    client, headers = api_client

    create_payload = {
        "symbol": "AAPL",
        "direction": "LONG",
        "asset_type": "stock",
        "strategy": "breakout",
        "thesis": "Trend continuation",
        "reason_entry": "Range break",
        "notes": "Contract test",
        "tags": "tech,momentum",
        "user_id": 1,
    }
    create_resp = await client.post("/trades/", json=create_payload, headers=headers)
    assert create_resp.status_code == 201
    trade = create_resp.json()
    trade_id = trade["id"]

    assert set(trade.keys()) == CANONICAL_TRADE_KEYS

    fill_payload = {
        "fill_datetime": "2026-03-08T10:00:00Z",
        "side": "BUY",
        "quantity": "5",
        "price": "100",
        "commission": "1",
        "source": "manual",
    }
    fill_resp = await client.post(f"/trades/{trade_id}/fills", json=fill_payload, headers=headers)
    assert fill_resp.status_code == 201

    list_resp = await client.get("/trades/", headers=headers)
    assert list_resp.status_code == 200
    trades = list_resp.json()
    assert len(trades) == 1
    assert set(trades[0].keys()) == CANONICAL_TRADE_KEYS
    assert isinstance(trades[0]["fills"], list)
    assert len(trades[0]["fills"]) == 1

    detail_resp = await client.get(f"/trades/{trade_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail_trade = detail_resp.json()
    assert set(detail_trade.keys()) == CANONICAL_TRADE_KEYS
    assert len(detail_trade["fills"]) == 1


@pytest.mark.anyio
async def test_legacy_fields_not_in_canonical_response(api_client) -> None:
    client, headers = api_client

    create_resp = await client.post(
        "/trades/",
        json={"symbol": "MSFT", "direction": "LONG", "user_id": 1},
        headers=headers,
    )
    assert create_resp.status_code == 201
    trade = create_resp.json()

    assert LEGACY_KEYS.isdisjoint(set(trade.keys()))

    detail_resp = await client.get(f"/trades/{trade['id']}", headers=headers)
    assert detail_resp.status_code == 200
    detail_trade = detail_resp.json()
    assert LEGACY_KEYS.isdisjoint(set(detail_trade.keys()))
