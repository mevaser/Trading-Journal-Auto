from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./_w2_t2_import_bootstrap.db")

from app.auth.tokens import issue_token_pair
from app.core.config import clear_settings_cache
from app.db.models import Base, Membership, Tenant, User
from app.db.session import get_db
from app.main import app


def _as_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _assert_decimal_field(payload: dict, field: str, expected: str | None) -> None:
    actual = payload[field]
    if expected is None:
        assert actual is None
        return
    assert actual is not None
    assert _as_decimal(actual) == Decimal(expected)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def api_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    clear_settings_cache()

    db_file = tmp_path / "test_w2_t2_trade_lifecycle.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_local() as session:
        tenant = Tenant(id=1, slug="default", name="Default", is_active=True)
        user = User(username="w2t2", email="w2t2@example.com", password_hash="x")
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
        yield client, headers

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()


async def _create_trade(client: AsyncClient, headers: dict[str, str], *, symbol: str = "AAPL", direction: str = "LONG") -> int:
    response = await client.post(
        "/trades/",
        json={"symbol": symbol, "direction": direction},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_fill(
    client: AsyncClient,
    headers: dict[str, str],
    trade_id: int,
    *,
    fill_datetime: str,
    side: str,
    quantity: str,
    price: str,
    commission: str = "0",
) -> dict:
    response = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": fill_datetime,
            "side": side,
            "quantity": quantity,
            "price": price,
            "commission": commission,
            "source": "manual",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def _get_trade(client: AsyncClient, headers: dict[str, str], trade_id: int) -> dict:
    response = await client.get(f"/trades/{trade_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


@pytest.mark.anyio
async def test_open_trade_after_entry_fills_only(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers, symbol="AMD")

    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-01T10:00:00Z",
        side="BUY",
        quantity="2",
        price="99",
    )
    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-01T11:00:00Z",
        side="BUY",
        quantity="3",
        price="101",
    )

    trade = await _get_trade(client, headers, trade_id)
    assert trade["status"] == "open"
    _assert_decimal_field(trade, "quantity_opened", "5")
    _assert_decimal_field(trade, "quantity_closed", "0")
    _assert_decimal_field(trade, "remaining_quantity", "5")
    _assert_decimal_field(trade, "avg_entry_price", "100.2")
    _assert_decimal_field(trade, "avg_exit_price", None)
    assert trade["closed_at"] is None


@pytest.mark.anyio
async def test_partial_close_after_mixed_entry_exit_fills(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers, symbol="MSFT")

    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-02T10:00:00Z",
        side="BUY",
        quantity="10",
        price="100",
    )
    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-02T11:00:00Z",
        side="SELL",
        quantity="4",
        price="110",
        commission="1",
    )

    trade = await _get_trade(client, headers, trade_id)
    assert trade["status"] == "partial"
    _assert_decimal_field(trade, "quantity_opened", "10")
    _assert_decimal_field(trade, "quantity_closed", "4")
    _assert_decimal_field(trade, "remaining_quantity", "6")
    _assert_decimal_field(trade, "avg_entry_price", "100")
    _assert_decimal_field(trade, "avg_exit_price", "110")
    assert trade["closed_at"] is None


@pytest.mark.anyio
async def test_trade_closes_when_remaining_quantity_reaches_zero(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers, symbol="TSLA")

    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-03T10:00:00Z",
        side="BUY",
        quantity="5",
        price="50",
    )
    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-03T15:00:00Z",
        side="SELL",
        quantity="5",
        price="55",
    )

    trade = await _get_trade(client, headers, trade_id)
    assert trade["status"] == "closed"
    _assert_decimal_field(trade, "quantity_opened", "5")
    _assert_decimal_field(trade, "quantity_closed", "5")
    _assert_decimal_field(trade, "remaining_quantity", "0")
    assert trade["closed_at"] is not None
    assert str(trade["closed_at"]).startswith("2026-02-03T15:00:00")


@pytest.mark.anyio
async def test_weighted_average_entry_price_behavior(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers, symbol="NVDA")

    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-04T10:00:00Z",
        side="BUY",
        quantity="10",
        price="100",
    )
    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-04T10:30:00Z",
        side="BUY",
        quantity="10",
        price="110",
    )

    trade = await _get_trade(client, headers, trade_id)
    _assert_decimal_field(trade, "avg_entry_price", "105")
    _assert_decimal_field(trade, "quantity_opened", "20")
    _assert_decimal_field(trade, "quantity_closed", "0")
    _assert_decimal_field(trade, "remaining_quantity", "20")
    assert trade["status"] == "open"


@pytest.mark.anyio
async def test_weighted_average_exit_price_behavior(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers, symbol="META")

    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-05T10:00:00Z",
        side="BUY",
        quantity="10",
        price="100",
    )
    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-05T11:00:00Z",
        side="SELL",
        quantity="4",
        price="105",
    )
    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-05T12:00:00Z",
        side="SELL",
        quantity="2",
        price="120",
    )

    trade = await _get_trade(client, headers, trade_id)
    _assert_decimal_field(trade, "avg_exit_price", "110")
    _assert_decimal_field(trade, "quantity_opened", "10")
    _assert_decimal_field(trade, "quantity_closed", "6")
    _assert_decimal_field(trade, "remaining_quantity", "4")
    assert trade["status"] == "partial"


@pytest.mark.anyio
async def test_over_close_rejected_via_api_error_envelope(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers, symbol="NFLX")

    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-06T10:00:00Z",
        side="BUY",
        quantity="2",
        price="100",
    )

    response = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": "2026-02-06T11:00:00Z",
            "side": "SELL",
            "quantity": "3",
            "price": "101",
            "commission": "0",
            "source": "manual",
        },
        headers=headers,
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "domain_validation"
    assert "closing quantity exceeds currently open quantity" in payload["error"]["message"]


@pytest.mark.anyio
async def test_close_before_open_rejected_via_api_error_envelope(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers, symbol="QQQ")

    response = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": "2026-02-07T09:30:00Z",
            "side": "SELL",
            "quantity": "1",
            "price": "350",
            "commission": "0",
            "source": "manual",
        },
        headers=headers,
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "domain_validation"
    assert "closing quantity exceeds currently open quantity" in payload["error"]["message"]


@pytest.mark.anyio
async def test_reopen_after_full_close_rejected_via_api_error_envelope(api_client) -> None:
    client, headers = api_client
    trade_id = await _create_trade(client, headers, symbol="SPY")

    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-08T10:00:00Z",
        side="BUY",
        quantity="2",
        price="400",
    )
    await _create_fill(
        client,
        headers,
        trade_id,
        fill_datetime="2026-02-08T11:00:00Z",
        side="SELL",
        quantity="2",
        price="410",
    )

    response = await client.post(
        f"/trades/{trade_id}/fills",
        json={
            "fill_datetime": "2026-02-08T12:00:00Z",
            "side": "BUY",
            "quantity": "1",
            "price": "405",
            "commission": "0",
            "source": "manual",
        },
        headers=headers,
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "domain_validation"
    assert "reopening a fully closed trade is not supported" in payload["error"]["message"]
