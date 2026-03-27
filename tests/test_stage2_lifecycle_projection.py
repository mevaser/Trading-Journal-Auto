from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.tokens import issue_token_pair
from app.core.config import clear_settings_cache
from app.db.models import (
    Base,
    BrokerExecutionFill,
    Membership,
    Tenant,
    TradeLifecycleExecutionAllocation,
    TradeLifecycleProjection,
    TradeLifecycleProjectionState,
    User,
)
from app.db.session import get_db
from app.main import app
from app.services.lifecycle_projection_service import LifecycleProjectionService
from app.services.lifecycle_projection_service import LifecycleProjectionPartition


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def api_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "stage2-projection-secret")
    clear_settings_cache()

    db_file = tmp_path / "test_stage2_projection.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_local() as session:
        session.add_all(
            [
                Tenant(id=1, slug="alpha", name="Alpha", is_active=True),
                Tenant(id=2, slug="beta", name="Beta", is_active=True),
                User(id=1, username="alpha-user", email="alpha@example.com", password_hash="x"),
                User(id=2, username="beta-user", email="beta@example.com", password_hash="x"),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Membership(tenant_id=1, user_id=1, role="owner", is_active=True),
                Membership(tenant_id=2, user_id=2, role="owner", is_active=True),
            ]
        )
        await session.commit()

    token_1 = issue_token_pair(user_id=1, tenant_id=1, roles=["owner"], secret_key="stage2-projection-secret")
    token_2 = issue_token_pair(user_id=2, tenant_id=2, roles=["owner"], secret_key="stage2-projection-secret")
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


def _payload(executions: list[dict], *, broker_account_id: str = "DU111") -> dict:
    return {
        "start_time": "2026-03-19T08:00:00Z",
        "end_time": "2026-03-19T22:00:00Z",
        "async_mode": False,
        "broker_account_id": broker_account_id,
        "executions": executions,
    }


async def _import(client: AsyncClient, headers: dict[str, str], executions: list[dict], *, broker_account_id: str = "DU111") -> dict:
    response = await client.post("/broker/ibkr/import", json=_payload(executions, broker_account_id=broker_account_id), headers=headers)
    assert response.status_code == 200
    return response.json()


async def _load_state(session, *, tenant_id: int, source: str = "ibkr", broker_account_id: str = "DU111", symbol: str = "AAPL", asset_type: str = "stock") -> TradeLifecycleProjectionState:
    stmt = select(TradeLifecycleProjectionState).where(
        TradeLifecycleProjectionState.tenant_id == tenant_id,
        TradeLifecycleProjectionState.source == source,
        TradeLifecycleProjectionState.broker_account_id == broker_account_id,
        TradeLifecycleProjectionState.symbol == symbol,
        TradeLifecycleProjectionState.asset_type == asset_type,
    )
    return (await session.execute(stmt)).scalar_one()


@pytest.mark.anyio
async def test_full_rebuild_persists_lifecycle_and_allocations(api_client) -> None:
    client, headers_1, _, session_local = api_client
    await _import(
        client,
        headers_1,
        [
            {
                "external_execution_id": "exec-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0",
                "execution_time": "2026-03-19T10:00:00Z",
            },
            {
                "external_execution_id": "exec-2",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "1",
                "price": "110",
                "commission": "0",
                "execution_time": "2026-03-19T12:00:00Z",
            },
        ],
    )

    async with session_local() as session:
        state = await _load_state(session, tenant_id=1)
        assert state.is_dirty is True

    async with session_local() as session:
        service = LifecycleProjectionService(session)
        results = await service.rebuild_dirty_partitions(tenant_id=1)
        assert len(results) == 1
        assert results[0].lifecycle_count == 1
        assert results[0].allocation_count == 2

    async with session_local() as session:
        lifecycle = (
            await session.execute(
                select(TradeLifecycleProjection)
                .where(TradeLifecycleProjection.tenant_id == 1)
                .order_by(TradeLifecycleProjection.lifecycle_seq.asc())
            )
        ).scalar_one()
        assert lifecycle.lifecycle_seq == 1
        assert lifecycle.direction == "LONG"
        assert lifecycle.status == "OPEN"
        assert str(lifecycle.entry_quantity) == "2.00000000"
        assert str(lifecycle.exit_quantity) == "1.00000000"
        assert str(lifecycle.remaining_quantity) == "1.00000000"

        allocations = list(
            (
                await session.execute(
                    select(TradeLifecycleExecutionAllocation)
                    .where(TradeLifecycleExecutionAllocation.trade_lifecycle_id == lifecycle.id)
                    .order_by(TradeLifecycleExecutionAllocation.allocation_seq.asc())
                )
            ).scalars()
        )
        assert [allocation.allocation_seq for allocation in allocations] == [1, 2]
        assert [allocation.allocation_role for allocation in allocations] == ["ENTRY", "EXIT"]
        assert [allocation.is_flip_slice for allocation in allocations] == [False, False]

        state = await _load_state(session, tenant_id=1)
        assert state.is_dirty is False
        assert state.current_generation == 1


@pytest.mark.anyio
async def test_incremental_rebuild_expands_to_spanning_lifecycle_boundary(api_client) -> None:
    client, headers_1, _, session_local = api_client
    await _import(
        client,
        headers_1,
        [
            {
                "external_execution_id": "exec-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "5",
                "price": "100",
                "commission": "0",
                "execution_time": "2026-03-19T10:00:00Z",
            },
            {
                "external_execution_id": "exec-2",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "2",
                "price": "110",
                "commission": "0",
                "execution_time": "2026-03-19T12:00:00Z",
            },
        ],
    )

    async with session_local() as session:
        await LifecycleProjectionService(session).rebuild_dirty_partitions(tenant_id=1)

    await _import(
        client,
        headers_1,
        [
            {
                "external_execution_id": "exec-3",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "3",
                "price": "115",
                "commission": "0",
                "execution_time": "2026-03-19T15:00:00Z",
            }
        ],
    )

    async with session_local() as session:
        state_before = await _load_state(session, tenant_id=1)
        assert str(state_before.earliest_dirty_execution_time_utc).startswith("2026-03-19 15:00:00")

    async with session_local() as session:
        results = await LifecycleProjectionService(session).rebuild_dirty_partitions(tenant_id=1)
        assert len(results) == 1
        assert str(results[0].rebuild_from_execution_time_utc).startswith("2026-03-19 10:00:00")

    async with session_local() as session:
        lifecycle = (
            await session.execute(select(TradeLifecycleProjection).where(TradeLifecycleProjection.tenant_id == 1))
        ).scalar_one()
        assert lifecycle.lifecycle_seq == 1
        assert lifecycle.status == "CLOSED"
        assert lifecycle.closed_at is not None
        assert str(lifecycle.exit_quantity) == "5.00000000"

        allocations = list(
            (
                await session.execute(
                    select(TradeLifecycleExecutionAllocation)
                    .where(TradeLifecycleExecutionAllocation.trade_lifecycle_id == lifecycle.id)
                    .order_by(TradeLifecycleExecutionAllocation.allocation_seq.asc())
                )
            ).scalars()
        )
        assert [allocation.allocation_seq for allocation in allocations] == [1, 2, 3]

        state_after = await _load_state(session, tenant_id=1)
        assert state_after.current_generation == 2
        assert state_after.is_dirty is False


@pytest.mark.anyio
async def test_load_canonical_rows_uses_spanning_lifecycle_opened_at(api_client) -> None:
    client, headers_1, _, session_local = api_client
    await _import(
        client,
        headers_1,
        [
            {
                "external_execution_id": "exec-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "5",
                "price": "100",
                "commission": "0",
                "execution_time": "2026-03-19T10:00:00Z",
            },
            {
                "external_execution_id": "exec-2",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "2",
                "price": "110",
                "commission": "0",
                "execution_time": "2026-03-19T12:00:00Z",
            },
        ],
    )

    async with session_local() as session:
        await LifecycleProjectionService(session).rebuild_dirty_partitions(tenant_id=1)

    async with session_local() as session:
        service = LifecycleProjectionService(session)
        rows = await service._load_canonical_rows(
            partition=LifecycleProjectionPartition(
                tenant_id=1,
                source="ibkr",
                broker_account_id="DU111",
                symbol="AAPL",
                asset_type="stock",
            ),
            boundary=datetime(2026, 3, 19, 12, 0, tzinfo=UTC),
        )
        assert [row.external_execution_id for row in rows] == ["exec-1", "exec-2"]


@pytest.mark.anyio
async def test_flip_execution_persists_split_allocations(api_client) -> None:
    client, headers_1, _, session_local = api_client
    await _import(
        client,
        headers_1,
        [
            {
                "external_execution_id": "exec-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "5",
                "price": "100",
                "commission": "0",
                "execution_time": "2026-03-19T10:00:00Z",
            },
            {
                "external_execution_id": "exec-2",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "7",
                "price": "90",
                "commission": "0",
                "execution_time": "2026-03-19T12:00:00Z",
            },
        ],
    )

    async with session_local() as session:
        await LifecycleProjectionService(session).rebuild_dirty_partitions(tenant_id=1)

    async with session_local() as session:
        lifecycles = list(
            (
                await session.execute(
                    select(TradeLifecycleProjection)
                    .where(TradeLifecycleProjection.tenant_id == 1)
                    .order_by(TradeLifecycleProjection.lifecycle_seq.asc())
                )
            ).scalars()
        )
        assert len(lifecycles) == 2
        assert [lifecycle.lifecycle_seq for lifecycle in lifecycles] == [1, 2]
        assert [lifecycle.direction for lifecycle in lifecycles] == ["LONG", "SHORT"]
        assert [lifecycle.status for lifecycle in lifecycles] == ["CLOSED", "OPEN"]
        assert str(lifecycles[0].remaining_quantity) == "0E-8"
        assert str(lifecycles[1].remaining_quantity) == "2.00000000"

        first_allocations = list(
            (
                await session.execute(
                    select(TradeLifecycleExecutionAllocation)
                    .where(TradeLifecycleExecutionAllocation.trade_lifecycle_id == lifecycles[0].id)
                    .order_by(TradeLifecycleExecutionAllocation.allocation_seq.asc())
                )
            ).scalars()
        )
        second_allocations = list(
            (
                await session.execute(
                    select(TradeLifecycleExecutionAllocation)
                    .where(TradeLifecycleExecutionAllocation.trade_lifecycle_id == lifecycles[1].id)
                    .order_by(TradeLifecycleExecutionAllocation.allocation_seq.asc())
                )
            ).scalars()
        )
        assert [(item.allocation_role, str(item.allocated_quantity), item.is_flip_slice) for item in first_allocations] == [
            ("ENTRY", "5.00000000", False),
            ("EXIT", "5.00000000", True),
        ]
        assert [(item.allocation_role, str(item.allocated_quantity), item.is_flip_slice) for item in second_allocations] == [
            ("ENTRY", "2.00000000", True),
        ]


@pytest.mark.anyio
async def test_supersede_marks_partition_dirty_and_rebuilds_from_earliest_impacted_time(api_client) -> None:
    client, headers_1, _, session_local = api_client
    await _import(
        client,
        headers_1,
        [
            {
                "external_execution_id": "exec-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "100",
                "commission": "0",
                "execution_time": "2026-03-19T10:00:00Z",
            },
            {
                "external_execution_id": "exec-2",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "1",
                "price": "110",
                "commission": "0",
                "execution_time": "2026-03-19T12:00:00Z",
            },
        ],
    )

    async with session_local() as session:
        await LifecycleProjectionService(session).rebuild_dirty_partitions(tenant_id=1)

    await _import(
        client,
        headers_1,
        [
            {
                "external_execution_id": "exec-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "1",
                "price": "101",
                "commission": "0",
                "execution_time": "2026-03-19T09:00:00Z",
            }
        ],
    )

    async with session_local() as session:
        state = await _load_state(session, tenant_id=1)
        assert str(state.earliest_dirty_execution_time_utc).startswith("2026-03-19 09:00:00")
        active_exec_1 = (
            await session.execute(
                select(BrokerExecutionFill)
                .where(
                    BrokerExecutionFill.tenant_id == 1,
                    BrokerExecutionFill.external_execution_id == "exec-1",
                    BrokerExecutionFill.is_active.is_(True),
                )
            )
        ).scalar_one()
        assert str(active_exec_1.price) == "101.00000000"

    async with session_local() as session:
        results = await LifecycleProjectionService(session).rebuild_dirty_partitions(tenant_id=1)
        assert len(results) == 1
        assert str(results[0].rebuild_from_execution_time_utc).startswith("2026-03-19 09:00:00")

    async with session_local() as session:
        lifecycle = (
            await session.execute(select(TradeLifecycleProjection).where(TradeLifecycleProjection.tenant_id == 1))
        ).scalar_one()
        assert str(lifecycle.opened_at).startswith("2026-03-19 09:00:00")
        assert str(lifecycle.avg_entry_price) == "101.00000000"


@pytest.mark.anyio
async def test_rebuild_dirty_partitions_respects_tenant_scope(api_client) -> None:
    client, headers_1, headers_2, session_local = api_client
    executions = [
        {
            "external_execution_id": "exec-1",
            "symbol": "AAPL",
            "side": "BUY",
            "asset_type": "stock",
            "quantity": "1",
            "price": "100",
            "commission": "0",
            "execution_time": "2026-03-19T10:00:00Z",
        }
    ]
    await _import(client, headers_1, executions)
    await _import(client, headers_2, executions)

    async with session_local() as session:
        results = await LifecycleProjectionService(session).rebuild_dirty_partitions(tenant_id=1)
        assert len(results) == 1
        assert results[0].partition.tenant_id == 1

    async with session_local() as session:
        tenant_1_state = await _load_state(session, tenant_id=1)
        tenant_2_state = await _load_state(session, tenant_id=2)
        assert tenant_1_state.is_dirty is False
        assert tenant_2_state.is_dirty is True

        tenant_1_lifecycles = list(
            (
                await session.execute(
                    select(TradeLifecycleProjection).where(TradeLifecycleProjection.tenant_id == 1)
                )
            ).scalars()
        )
        tenant_2_lifecycles = list(
            (
                await session.execute(
                    select(TradeLifecycleProjection).where(TradeLifecycleProjection.tenant_id == 2)
                )
            ).scalars()
        )
        assert len(tenant_1_lifecycles) == 1
        assert tenant_2_lifecycles == []
