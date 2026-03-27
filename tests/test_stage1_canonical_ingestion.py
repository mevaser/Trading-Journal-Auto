from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.tokens import issue_token_pair
from app.brokers.ibkr.dto import AssetType, ExecutionDTO, ExecutionSide
from app.core.config import clear_settings_cache
from app.db.models import (
    Base,
    BrokerExecutionFill,
    ImportRun,
    ImportRunRecord,
    JobRun,
    Membership,
    Tenant,
    Trade,
    TradeFill,
    User,
)
from app.db.session import get_db
from app.main import app
from app.services.execution_ingestion import normalize_execution, payload_hash
from app.services.projection_service import ProjectionService
from app.worker import tasks as worker_tasks


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def api_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "stage1-import-secret")
    clear_settings_cache()

    db_file = tmp_path / "test_stage1_import.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_local() as session:
        t1 = Tenant(id=1, slug="alpha", name="Alpha", is_active=True)
        t2 = Tenant(id=2, slug="beta", name="Beta", is_active=True)
        u1 = User(id=1, username="alpha-user", email="alpha@example.com", password_hash="x")
        u2 = User(id=2, username="beta-user", email="beta@example.com", password_hash="x")
        session.add_all([t1, t2, u1, u2])
        await session.flush()
        session.add_all(
            [
                Membership(tenant_id=1, user_id=1, role="owner", is_active=True),
                Membership(tenant_id=2, user_id=2, role="owner", is_active=True),
            ]
        )
        await session.commit()

    token_1 = issue_token_pair(user_id=1, tenant_id=1, roles=["owner"], secret_key="stage1-import-secret")
    token_2 = issue_token_pair(user_id=2, tenant_id=2, roles=["owner"], secret_key="stage1-import-secret")
    headers_1 = {"Authorization": f"Bearer {token_1.access_token}", "X-Tenant-ID": "1"}
    headers_2 = {"Authorization": f"Bearer {token_2.access_token}", "X-Tenant-ID": "2"}

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, headers_1, headers_2, test_session_local

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()


def _payload(*, broker_account_id: str | None = "DU111", executions: list[dict] | None = None) -> dict:
    return {
        "start_time": "2026-03-19T08:00:00Z",
        "end_time": "2026-03-19T22:00:00Z",
        "async_mode": False,
        "broker_account_id": broker_account_id,
        "executions": executions
        or [
            {
                "external_execution_id": "exec-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            },
            {
                "external_execution_id": "exec-2",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "1",
                "price": "110",
                "commission": "0.5",
                "execution_time": "2026-03-19T12:00:00Z",
            },
        ],
    }


async def _count_rows(session: AsyncSession, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


@pytest.mark.anyio
async def test_exact_duplicate_replay_creates_duplicate_skipped_only(api_client) -> None:
    client, headers_1, _, session_local = api_client

    first = await client.post("/broker/ibkr/import", json=_payload(), headers=headers_1)
    assert first.status_code == 200
    first_summary = first.json()["summary"]
    assert first_summary["imported"] == 2
    assert first_summary["duplicates_skipped"] == 0

    second = await client.post("/broker/ibkr/import", json=_payload(), headers=headers_1)
    assert second.status_code == 200
    second_payload = second.json()
    second_summary = second_payload["summary"]
    assert second_summary["imported"] == 0
    assert second_summary["duplicates_skipped"] == 2

    async with session_local() as session:
        canonical_count = await _count_rows(session, BrokerExecutionFill)
        assert canonical_count == 2

        run_id = second_payload["import_run_id"]
        records = list(
            (
                await session.execute(
                    select(ImportRunRecord).where(ImportRunRecord.import_run_id == run_id)
                )
            ).scalars()
        )
        assert len(records) == 2
        assert all(record.status == "duplicate_skipped" for record in records)
        assert all(record.canonical_execution_fill_id is not None for record in records)
        assert all(record.resolved_at is not None for record in records)


@pytest.mark.anyio
async def test_same_identity_changed_payload_supersedes_with_lineage(api_client) -> None:
    client, headers_1, _, session_local = api_client

    p1 = _payload(
        executions=[
            {
                "external_execution_id": "exec-42",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "100",
                "commission": "0",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )
    r1 = await client.post("/broker/ibkr/import", json=p1, headers=headers_1)
    assert r1.status_code == 200

    p2 = _payload(
        executions=[
            {
                "external_execution_id": "exec-42",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "101",
                "commission": "0",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )
    r2 = await client.post("/broker/ibkr/import", json=p2, headers=headers_1)
    assert r2.status_code == 200
    assert r2.json()["summary"]["imported"] == 1

    async with session_local() as session:
        rows = list(
            (
                await session.execute(
                    select(BrokerExecutionFill)
                    .where(BrokerExecutionFill.external_execution_id == "exec-42")
                    .order_by(BrokerExecutionFill.id.asc())
                )
            ).scalars()
        )
        assert len(rows) == 2
        old_row, new_row = rows
        assert old_row.is_active is False
        assert new_row.is_active is True
        assert new_row.supersedes_execution_fill_id == old_row.id
        assert old_row.superseded_by_execution_fill_id == new_row.id

        run_id = r2.json()["import_run_id"]
        record = (
            await session.execute(
                select(ImportRunRecord).where(ImportRunRecord.import_run_id == run_id)
            )
        ).scalar_one()
        assert record.status == "resolved_superseded"
        assert record.canonical_execution_fill_id == new_row.id
        assert record.resolved_at is not None


def test_commission_null_vs_zero_produces_same_payload_hash() -> None:
    ts = datetime(2026, 3, 19, 10, 0, tzinfo=UTC)

    no_comm = ExecutionDTO(
        external_execution_id="exec-comm",
        symbol="AAPL",
        side=ExecutionSide.BUY,
        asset_type=AssetType.STOCK,
        quantity=Decimal("1"),
        price=Decimal("100"),
        execution_time=ts,
        commission=None,
        account_id="DU111",
    )
    zero_comm = ExecutionDTO(
        external_execution_id="exec-comm",
        symbol="AAPL",
        side=ExecutionSide.BUY,
        asset_type=AssetType.STOCK,
        quantity=Decimal("1"),
        price=Decimal("100"),
        execution_time=ts,
        commission=Decimal("0"),
        account_id="DU111",
    )

    n1 = normalize_execution(no_comm, source="ibkr", default_broker_account_id=None)
    n2 = normalize_execution(zero_comm, source="ibkr", default_broker_account_id=None)

    assert payload_hash(n1, tenant_id=1) == payload_hash(n2, tenant_id=1)


@pytest.mark.anyio
async def test_deterministic_ordering_assigns_stable_record_seq(api_client) -> None:
    client, headers_1, _, session_local = api_client

    payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-b",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "101",
                "commission": "0",
                "execution_time": "2026-03-19T11:00:00Z",
            },
            {
                "external_execution_id": "exec-a",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "100",
                "commission": "0",
                "execution_time": "2026-03-19T11:00:00Z",
            },
            {
                "external_execution_id": "exec-0",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "99",
                "commission": "0",
                "execution_time": "2026-03-19T10:59:00Z",
            },
        ]
    )

    response = await client.post("/broker/ibkr/import", json=payload, headers=headers_1)
    assert response.status_code == 200
    run_id = response.json()["import_run_id"]

    async with session_local() as session:
        rows = list(
            (
                await session.execute(
                    select(ImportRunRecord)
                    .where(ImportRunRecord.import_run_id == run_id)
                    .order_by(ImportRunRecord.record_seq.asc())
                )
            ).scalars()
        )
        assert [row.external_execution_id for row in rows] == ["exec-0", "exec-a", "exec-b"]
        assert [row.record_seq for row in rows] == [1, 2, 3]


@pytest.mark.anyio
async def test_terminal_statuses_set_ids_and_resolved_at_and_failed_validation_is_null(api_client) -> None:
    client, headers_1, _, session_local = api_client

    valid = await client.post("/broker/ibkr/import", json=_payload(), headers=headers_1)
    assert valid.status_code == 200
    valid_run_id = valid.json()["import_run_id"]

    invalid = await client.post(
        "/broker/ibkr/import",
        json=_payload(
            broker_account_id=None,
            executions=[
                {
                    "external_execution_id": "bad-1",
                    "symbol": "AAPL",
                    "side": "BUY",
                    "asset_type": "stock",
                    "quantity": "1",
                    "price": "100",
                    "commission": "0",
                    "execution_time": "2026-03-19T10:00:00Z",
                }
            ],
        ),
        headers=headers_1,
    )
    assert invalid.status_code == 422

    async with session_local() as session:
        ok_records = list(
            (
                await session.execute(
                    select(ImportRunRecord).where(ImportRunRecord.import_run_id == valid_run_id)
                )
            ).scalars()
        )
        assert ok_records
        assert all(record.status in {"resolved_inserted", "duplicate_skipped", "resolved_superseded"} for record in ok_records)
        assert all(record.canonical_execution_fill_id is not None for record in ok_records)
        assert all(record.resolved_at is not None for record in ok_records)


@pytest.mark.anyio
async def test_stage1_import_projects_trade_and_trade_fill_for_resolved_inserted(api_client) -> None:
    client, headers_1, _, session_local = api_client

    async with session_local() as session:
        before_trades = await _count_rows(session, Trade)
        before_fills = await _count_rows(session, TradeFill)
        assert before_trades == 0
        assert before_fills == 0

    payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )

    response = await client.post("/broker/ibkr/import", json=payload, headers=headers_1)
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["projected_trades_created"] == 1
    assert summary["projected_trades_updated"] == 0
    assert summary["projected_fills_created"] == 1
    assert summary["projection_failures"] == 0

    async with session_local() as session:
        after_trades = await _count_rows(session, Trade)
        after_fills = await _count_rows(session, TradeFill)
        assert after_trades == 1
        assert after_fills == 1

        trade = (await session.execute(select(Trade))).scalar_one()
        fill = (await session.execute(select(TradeFill))).scalar_one()
        canonical_fill = (await session.execute(select(BrokerExecutionFill))).scalar_one()

        assert trade.tenant_id == 1
        assert trade.symbol == "AAPL"
        assert trade.status == "open"

        assert fill.trade_id == trade.id
        assert fill.tenant_id == trade.tenant_id
        assert fill.external_fill_id == "exec-live-1"
        assert fill.canonical_execution_fill_id == canonical_fill.id


@pytest.mark.anyio
async def test_stage1_replay_does_not_duplicate_projected_trade_or_fill(api_client) -> None:
    client, headers_1, _, session_local = api_client

    payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-replay-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )

    first = await client.post("/broker/ibkr/import", json=payload, headers=headers_1)
    assert first.status_code == 200

    replay = await client.post("/broker/ibkr/import", json=payload, headers=headers_1)
    assert replay.status_code == 200

    async with session_local() as session:
        trade_count = await _count_rows(session, Trade)
        fill_count = await _count_rows(session, TradeFill)
        canonical_count = await _count_rows(session, BrokerExecutionFill)

        assert trade_count == 1
        assert fill_count == 1
        assert canonical_count == 1

        fill = (await session.execute(select(TradeFill))).scalar_one()
        canonical_fill = (await session.execute(select(BrokerExecutionFill))).scalar_one()
        assert fill.canonical_execution_fill_id == canonical_fill.id


@pytest.mark.anyio
async def test_stage1_superseded_import_logs_and_does_not_add_projected_fill(api_client, caplog) -> None:
    client, headers_1, _, session_local = api_client

    first_payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-supersede-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )
    second_payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-supersede-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "101",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )

    first = await client.post("/broker/ibkr/import", json=first_payload, headers=headers_1)
    assert first.status_code == 200

    with caplog.at_level("WARNING", logger="app.import.projection"):
        second = await client.post("/broker/ibkr/import", json=second_payload, headers=headers_1)
    assert second.status_code == 200
    assert second.json()["summary"]["imported"] == 1

    async with session_local() as session:
        trade_count = await _count_rows(session, Trade)
        fill_count = await _count_rows(session, TradeFill)
        canonical_count = await _count_rows(session, BrokerExecutionFill)

        assert trade_count == 1
        assert fill_count == 1
        assert canonical_count == 2

        active_fill = (
            await session.execute(
                select(BrokerExecutionFill).where(
                    BrokerExecutionFill.external_execution_id == "exec-live-supersede-1",
                    BrokerExecutionFill.is_active.is_(True),
                )
            )
        ).scalar_one()
        projected_fill = (await session.execute(select(TradeFill))).scalar_one()
        assert projected_fill.canonical_execution_fill_id != active_fill.id

    supersede_logs = [record for record in caplog.records if record.message == "projection_superseded_deferred"]
    assert len(supersede_logs) == 1
    log_record = supersede_logs[0]
    assert log_record.record_seq == 1
    assert log_record.external_execution_id == "exec-live-supersede-1"
    assert log_record.canonical_execution_fill_id == active_fill.id
    assert log_record.superseded_canonical_execution_fill_id == projected_fill.canonical_execution_fill_id
    assert log_record.projected_fill_exists is True
    assert log_record.tenant_id == 1


@pytest.mark.anyio
async def test_stage1_import_projects_into_existing_open_trade_for_updated_path(api_client) -> None:
    client, headers_1, _, session_local = api_client

    async with session_local() as session:
        existing_trade = Trade(
            tenant_id=1,
            user_id=1,
            symbol="AAPL",
            asset_type="stock",
            direction="LONG",
            status="open",
        )
        session.add(existing_trade)
        await session.flush()
        existing_trade_id = existing_trade.id
        await session.commit()

    payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-updated-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )

    response = await client.post("/broker/ibkr/import", json=payload, headers=headers_1)
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["projected_trades_created"] == 0
    assert summary["projected_trades_updated"] == 1
    assert summary["projected_fills_created"] == 1
    assert summary["projection_failures"] == 0

    async with session_local() as session:
        trade_count = await _count_rows(session, Trade)
        fill_count = await _count_rows(session, TradeFill)

        assert trade_count == 1
        assert fill_count == 1

        fill = (await session.execute(select(TradeFill))).scalar_one()
        assert fill.trade_id == existing_trade_id
        assert fill.external_fill_id == "exec-live-updated-1"


@pytest.mark.anyio
async def test_stage1_multiple_imported_fills_attach_to_same_existing_trade(api_client) -> None:
    client, headers_1, _, session_local = api_client

    async with session_local() as session:
        existing_trade = Trade(
            tenant_id=1,
            user_id=1,
            symbol="AAPL",
            asset_type="stock",
            direction="LONG",
            status="open",
        )
        session.add(existing_trade)
        await session.flush()
        existing_trade_id = existing_trade.id
        await session.commit()

    first_payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-multi-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )
    second_payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-multi-2",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "3",
                "price": "102",
                "commission": "0.5",
                "execution_time": "2026-03-19T11:00:00Z",
            }
        ]
    )

    first = await client.post("/broker/ibkr/import", json=first_payload, headers=headers_1)
    assert first.status_code == 200

    second = await client.post("/broker/ibkr/import", json=second_payload, headers=headers_1)
    assert second.status_code == 200

    async with session_local() as session:
        trade_count = await _count_rows(session, Trade)
        fill_count = await _count_rows(session, TradeFill)
        fills = list(
            (
                await session.execute(
                    select(TradeFill)
                    .where(TradeFill.trade_id == existing_trade_id)
                    .order_by(TradeFill.fill_datetime.asc(), TradeFill.id.asc())
                )
            ).scalars()
        )

        assert trade_count == 1
        assert fill_count == 2
        assert len(fills) == 2
        assert all(fill.trade_id == existing_trade_id for fill in fills)
        assert [fill.external_fill_id for fill in fills] == ["exec-live-multi-1", "exec-live-multi-2"]


@pytest.mark.anyio
async def test_stage1_partial_close_recalculates_projected_trade_metrics(api_client) -> None:
    client, headers_1, _, session_local = api_client

    opening_payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-partial-open",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "5",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )
    partial_close_payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-partial-close",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "2",
                "price": "110",
                "commission": "0.5",
                "execution_time": "2026-03-19T12:00:00Z",
            }
        ]
    )

    opening = await client.post("/broker/ibkr/import", json=opening_payload, headers=headers_1)
    assert opening.status_code == 200

    partial_close = await client.post("/broker/ibkr/import", json=partial_close_payload, headers=headers_1)
    assert partial_close.status_code == 200

    async with session_local() as session:
        trade_count = await _count_rows(session, Trade)
        fill_count = await _count_rows(session, TradeFill)
        trade = (await session.execute(select(Trade))).scalar_one()

        assert trade_count == 1
        assert fill_count == 2
        assert trade.status == "partial"
        assert trade.remaining_quantity == Decimal("3.00000000")
        assert trade.quantity_closed == Decimal("2.00000000")


@pytest.mark.anyio
async def test_stage1_full_close_recalculates_projected_trade_metrics(api_client) -> None:
    client, headers_1, _, session_local = api_client

    opening_payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-full-close-open",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "5",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )
    full_close_payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-full-close-exit",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "5",
                "price": "112",
                "commission": "0.5",
                "execution_time": "2026-03-19T14:00:00Z",
            }
        ]
    )

    opening = await client.post("/broker/ibkr/import", json=opening_payload, headers=headers_1)
    assert opening.status_code == 200

    full_close = await client.post("/broker/ibkr/import", json=full_close_payload, headers=headers_1)
    assert full_close.status_code == 200

    async with session_local() as session:
        trade_count = await _count_rows(session, Trade)
        fill_count = await _count_rows(session, TradeFill)
        trade = (await session.execute(select(Trade))).scalar_one()

        assert trade_count == 1
        assert fill_count == 2
        assert trade.status == "closed"
        assert trade.remaining_quantity == Decimal("0E-8")
        assert trade.closed_at is not None


@pytest.mark.anyio
async def test_stage1_import_projection_respects_tenant_isolation(api_client) -> None:
    client, headers_1, headers_2, session_local = api_client

    async with session_local() as session:
        tenant_a_trade = Trade(
            tenant_id=1,
            user_id=1,
            symbol="AAPL",
            asset_type="stock",
            direction="LONG",
            status="open",
        )
        session.add(tenant_a_trade)
        await session.flush()
        tenant_a_trade_id = tenant_a_trade.id
        await session.commit()

    payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-tenant-b-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ]
    )

    response = await client.post("/broker/ibkr/import", json=payload, headers=headers_2)
    assert response.status_code == 200

    async with session_local() as session:
        trades = list(
            (
                await session.execute(select(Trade).order_by(Trade.tenant_id.asc(), Trade.id.asc()))
            ).scalars()
        )
        fills = list(
            (
                await session.execute(select(TradeFill).order_by(TradeFill.tenant_id.asc(), TradeFill.id.asc()))
            ).scalars()
        )

        assert len(trades) == 2
        assert len(fills) == 1

        tenant_a_trades = [trade for trade in trades if trade.tenant_id == 1]
        tenant_b_trades = [trade for trade in trades if trade.tenant_id == 2]
        assert len(tenant_a_trades) == 1
        assert len(tenant_b_trades) == 1

        tenant_b_trade = tenant_b_trades[0]
        tenant_b_fill = fills[0]

        assert tenant_a_trades[0].id == tenant_a_trade_id
        assert tenant_b_trade.id != tenant_a_trade_id
        assert tenant_b_fill.trade_id == tenant_b_trade.id
        assert tenant_b_fill.tenant_id == 2
        assert tenant_b_fill.trade_id != tenant_a_trade_id


@pytest.mark.anyio
async def test_async_worker_import_projects_trade_and_trade_fill(api_client, monkeypatch) -> None:
    _, _, _, session_local = api_client
    monkeypatch.setattr(worker_tasks, "AsyncSessionLocal", session_local)

    async with session_local() as session:
        import_run = ImportRun(
            tenant_id=1,
            user_id=1,
            source="ibkr",
            broker_account_id="DU111",
            status="pending",
            window_start=datetime(2026, 3, 19, 8, 0, tzinfo=UTC),
            window_end=datetime(2026, 3, 19, 22, 0, tzinfo=UTC),
        )
        session.add(import_run)
        await session.flush()

        job_run = JobRun(
            tenant_id=1,
            user_id=1,
            import_run_id=import_run.id,
            external_job_id="task-async-1",
            status="queued",
        )
        session.add(job_run)
        await session.commit()
        import_run_id = import_run.id

    result = await worker_tasks._run_import_task(
        task_id="task-async-1",
        import_run_id=import_run_id,
        tenant_id=1,
        user_id=1,
        start_time="2026-03-19T08:00:00+00:00",
        end_time="2026-03-19T22:00:00+00:00",
        account_ref=None,
        broker_account_id="DU111",
        source="ibkr",
        inline_executions=[
            {
                "external_execution_id": "exec-async-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            }
        ],
    )

    assert result["status"] == "completed"

    async with session_local() as session:
        trade_count = await _count_rows(session, Trade)
        fill_count = await _count_rows(session, TradeFill)
        job = (
            await session.execute(
                select(JobRun).where(JobRun.external_job_id == "task-async-1")
            )
        ).scalar_one()
        run = (
            await session.execute(select(ImportRun).where(ImportRun.id == import_run_id))
        ).scalar_one()

        assert trade_count == 1
        assert fill_count == 1
        assert job.status == "completed"
        assert run.status == "completed"


@pytest.mark.anyio
async def test_stage1_projection_failure_is_row_level_and_import_continues(api_client, monkeypatch, caplog) -> None:
    client, headers_1, _, session_local = api_client

    original_apply_resolution = ProjectionService.apply_resolution

    async def failing_apply_resolution(self, session, execution, resolution, tenant_id, user_id, canonical_execution_fill_id=None):
        if execution.external_execution_id == "exec-live-projection-fail":
            raise RuntimeError("forced projection failure for test")
        return await original_apply_resolution(
            self,
            session,
            execution,
            resolution,
            tenant_id,
            user_id,
            canonical_execution_fill_id=canonical_execution_fill_id,
        )

    monkeypatch.setattr(ProjectionService, "apply_resolution", failing_apply_resolution)

    payload = _payload(
        executions=[
            {
                "external_execution_id": "exec-live-ok-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            },
            {
                "external_execution_id": "exec-live-projection-fail",
                "symbol": "MSFT",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "200",
                "commission": "0.5",
                "execution_time": "2026-03-19T11:00:00Z",
            },
            {
                "external_execution_id": "exec-live-ok-2",
                "symbol": "GOOG",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "300",
                "commission": "0.5",
                "execution_time": "2026-03-19T12:00:00Z",
            },
        ]
    )

    with caplog.at_level("WARNING", logger="app.import.projection"):
        response = await client.post("/broker/ibkr/import", json=payload, headers=headers_1)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["summary"]["imported"] == 3
    assert body["summary"]["failed"] == 0
    assert body["summary"]["projected_trades_created"] == 2
    assert body["summary"]["projected_trades_updated"] == 0
    assert body["summary"]["projected_fills_created"] == 2
    assert body["summary"]["projection_failures"] == 1

    async with session_local() as session:
        trade_count = await _count_rows(session, Trade)
        fill_count = await _count_rows(session, TradeFill)
        canonical_count = await _count_rows(session, BrokerExecutionFill)
        fills = list(
            (
                await session.execute(
                    select(TradeFill).order_by(TradeFill.fill_datetime.asc(), TradeFill.id.asc())
                )
            ).scalars()
        )
        records = list(
            (
                await session.execute(
                    select(ImportRunRecord)
                    .where(ImportRunRecord.import_run_id == body["import_run_id"])
                    .order_by(ImportRunRecord.record_seq.asc())
                )
            ).scalars()
        )

        assert canonical_count == 3
        assert trade_count == 2
        assert fill_count == 2
        assert [record.status for record in records] == [
            "resolved_inserted",
            "resolved_inserted",
            "resolved_inserted",
        ]
        assert [fill.external_fill_id for fill in fills] == ["exec-live-ok-1", "exec-live-ok-2"]
        assert all(fill.external_fill_id != "exec-live-projection-fail" for fill in fills)

    failure_logs = [record for record in caplog.records if record.message == "projection_failed"]
    assert len(failure_logs) == 1
    log_record = failure_logs[0]
    assert log_record.record_seq == 2
    assert log_record.external_execution_id == "exec-live-projection-fail"
    assert log_record.error == "forced projection failure for test"
    assert log_record.tenant_id == 1


@pytest.mark.anyio
async def test_import_run_tenant_scoping_still_holds(api_client) -> None:
    client, headers_1, headers_2, session_local = api_client

    created = await client.post("/broker/ibkr/import", json=_payload(), headers=headers_1)
    assert created.status_code == 200
    run_id = created.json()["import_run_id"]

    cross_tenant = await client.get(f"/imports/{run_id}", headers=headers_2)
    assert cross_tenant.status_code == 404

    async with session_local() as session:
        run = (
            await session.execute(select(ImportRun).where(ImportRun.id == run_id))
        ).scalar_one()
        assert run.tenant_id == 1
