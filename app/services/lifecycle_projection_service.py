from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from contextlib import asynccontextmanager
from typing import Iterable

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BrokerExecutionFill,
    TradeLifecycleExecutionAllocation,
    TradeLifecycleProjection,
    TradeLifecycleProjectionState,
)
from app.domain.trades.lifecycle_projection import CanonicalExecutionRow, build_persisted_lifecycles


PROJECTION_VERSION = 1


@dataclass(frozen=True)
class LifecycleProjectionPartition:
    tenant_id: int
    source: str
    broker_account_id: str
    symbol: str
    asset_type: str


@dataclass(frozen=True)
class RebuildResult:
    partition: LifecycleProjectionPartition
    rebuild_from_execution_time_utc: datetime | None
    lifecycle_count: int
    allocation_count: int
    generation: int


async def mark_partition_dirty_for_canonical(
    db: AsyncSession,
    *,
    canonical_execution_fill: BrokerExecutionFill,
    previous_active_fill: BrokerExecutionFill | None = None,
) -> TradeLifecycleProjectionState:
    """Mark one partition dirty after canonical state changes."""
    partition = LifecycleProjectionPartition(
        tenant_id=canonical_execution_fill.tenant_id,
        source=canonical_execution_fill.source,
        broker_account_id=canonical_execution_fill.broker_account_id,
        symbol=canonical_execution_fill.symbol,
        asset_type=canonical_execution_fill.asset_type,
    )
    state = await _get_or_create_projection_state(db, partition=partition)
    dirty_time = canonical_execution_fill.execution_time_utc
    if previous_active_fill is not None and previous_active_fill.execution_time_utc < dirty_time:
        dirty_time = previous_active_fill.execution_time_utc

    state.is_dirty = True
    if (
        state.earliest_dirty_execution_time_utc is None
        or dirty_time < state.earliest_dirty_execution_time_utc
    ):
        state.earliest_dirty_execution_time_utc = dirty_time
    await db.flush()
    return state


class LifecycleProjectionService:
    """Rebuilds persisted lifecycle projections from canonical execution fills."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def rebuild_partition_full(self, partition: LifecycleProjectionPartition) -> RebuildResult:
        await _prepare_rebuild_transaction(self.db)
        async with _transaction_scope(self.db):
            state = await _get_or_create_projection_state(self.db, partition=partition)
            result = await self._rebuild_partition(
                state=state,
                rebuild_from_execution_time_utc=None,
            )
        return result

    async def rebuild_dirty_partitions(
        self,
        *,
        tenant_id: int | None = None,
        limit: int | None = None,
    ) -> list[RebuildResult]:
        await _prepare_rebuild_transaction(self.db)
        async with _transaction_scope(self.db):
            stmt = (
                select(TradeLifecycleProjectionState)
                .where(TradeLifecycleProjectionState.is_dirty.is_(True))
                .order_by(
                    TradeLifecycleProjectionState.tenant_id.asc(),
                    TradeLifecycleProjectionState.source.asc(),
                    TradeLifecycleProjectionState.broker_account_id.asc(),
                    TradeLifecycleProjectionState.symbol.asc(),
                    TradeLifecycleProjectionState.asset_type.asc(),
                )
            )
            if tenant_id is not None:
                stmt = stmt.where(TradeLifecycleProjectionState.tenant_id == tenant_id)
            if limit is not None:
                stmt = stmt.limit(limit)

            states = list((await self.db.execute(stmt)).scalars().all())
            results: list[RebuildResult] = []
            for state in states:
                results.append(
                    await self._rebuild_partition(
                        state=state,
                        rebuild_from_execution_time_utc=state.earliest_dirty_execution_time_utc,
                    )
                )
        return results

    async def _rebuild_partition(
        self,
        *,
        state: TradeLifecycleProjectionState,
        rebuild_from_execution_time_utc: datetime | None,
    ) -> RebuildResult:
        partition = LifecycleProjectionPartition(
            tenant_id=state.tenant_id,
            source=state.source,
            broker_account_id=state.broker_account_id,
            symbol=state.symbol,
            asset_type=state.asset_type,
        )
        boundary = await self._resolve_boundary(partition=partition, requested_time=rebuild_from_execution_time_utc)
        generation = state.current_generation + 1
        await self._delete_suffix(partition=partition, boundary=boundary)
        canonical_rows = await self._load_canonical_rows(partition=partition, boundary=boundary)
        lifecycles = build_persisted_lifecycles(canonical_rows)
        lifecycle_count, allocation_count = await self._insert_lifecycles(
            state=state,
            partition=partition,
            generation=generation,
            lifecycles=lifecycles,
            boundary=boundary,
        )
        state.current_generation = generation
        state.projection_version = PROJECTION_VERSION
        state.is_dirty = False
        state.earliest_dirty_execution_time_utc = None
        state.last_rebuilt_at = datetime.now(UTC)
        state.last_rebuild_from_execution_time_utc = boundary
        if canonical_rows:
            last_row = canonical_rows[-1]
            state.last_canonical_execution_fill_id = last_row.canonical_execution_fill_id
            state.last_canonical_execution_time_utc = last_row.execution_time_utc
        else:
            state.last_canonical_execution_fill_id = None
            state.last_canonical_execution_time_utc = None
        await self.db.flush()
        return RebuildResult(
            partition=partition,
            rebuild_from_execution_time_utc=boundary,
            lifecycle_count=lifecycle_count,
            allocation_count=allocation_count,
            generation=generation,
        )

    async def _resolve_boundary(
        self,
        *,
        partition: LifecycleProjectionPartition,
        requested_time: datetime | None,
    ) -> datetime | None:
        if requested_time is None:
            return None

        spanning_stmt = (
            select(TradeLifecycleProjection)
            .where(
                TradeLifecycleProjection.tenant_id == partition.tenant_id,
                TradeLifecycleProjection.source == partition.source,
                TradeLifecycleProjection.broker_account_id == partition.broker_account_id,
                TradeLifecycleProjection.symbol == partition.symbol,
                TradeLifecycleProjection.asset_type == partition.asset_type,
                TradeLifecycleProjection.opened_at <= requested_time,
                or_(
                    TradeLifecycleProjection.closed_at.is_(None),
                    TradeLifecycleProjection.closed_at >= requested_time,
                ),
            )
            .order_by(TradeLifecycleProjection.opened_at.desc(), TradeLifecycleProjection.lifecycle_seq.desc())
            .limit(1)
        )
        spanning = (await self.db.execute(spanning_stmt)).scalar_one_or_none()
        if spanning is not None:
            return spanning.opened_at
        return requested_time

    async def _delete_suffix(
        self,
        *,
        partition: LifecycleProjectionPartition,
        boundary: datetime | None,
    ) -> None:
        lifecycle_ids_stmt = select(TradeLifecycleProjection.id).where(
            TradeLifecycleProjection.tenant_id == partition.tenant_id,
            TradeLifecycleProjection.source == partition.source,
            TradeLifecycleProjection.broker_account_id == partition.broker_account_id,
            TradeLifecycleProjection.symbol == partition.symbol,
            TradeLifecycleProjection.asset_type == partition.asset_type,
        )
        if boundary is not None:
            lifecycle_ids_stmt = lifecycle_ids_stmt.where(TradeLifecycleProjection.opened_at >= boundary)

        lifecycle_ids = list((await self.db.execute(lifecycle_ids_stmt)).scalars().all())
        if lifecycle_ids:
            await self.db.execute(
                delete(TradeLifecycleExecutionAllocation).where(
                    TradeLifecycleExecutionAllocation.trade_lifecycle_id.in_(lifecycle_ids)
                )
            )
            await self.db.execute(delete(TradeLifecycleProjection).where(TradeLifecycleProjection.id.in_(lifecycle_ids)))

    async def _load_canonical_rows(
        self,
        *,
        partition: LifecycleProjectionPartition,
        boundary: datetime | None,
    ) -> list[CanonicalExecutionRow]:
        effective_boundary = boundary
        if boundary is not None:
            spanning_stmt = (
                select(TradeLifecycleProjection.opened_at)
                .where(
                    TradeLifecycleProjection.tenant_id == partition.tenant_id,
                    TradeLifecycleProjection.source == partition.source,
                    TradeLifecycleProjection.broker_account_id == partition.broker_account_id,
                    TradeLifecycleProjection.symbol == partition.symbol,
                    TradeLifecycleProjection.asset_type == partition.asset_type,
                    TradeLifecycleProjection.opened_at <= boundary,
                    or_(
                        TradeLifecycleProjection.closed_at.is_(None),
                        TradeLifecycleProjection.closed_at >= boundary,
                    ),
                )
                .order_by(TradeLifecycleProjection.opened_at.desc(), TradeLifecycleProjection.lifecycle_seq.desc())
                .limit(1)
            )
            spanning_opened_at = (await self.db.execute(spanning_stmt)).scalar_one_or_none()
            if spanning_opened_at is not None:
                effective_boundary = spanning_opened_at

        stmt = (
            select(BrokerExecutionFill)
            .where(
                BrokerExecutionFill.tenant_id == partition.tenant_id,
                BrokerExecutionFill.source == partition.source,
                BrokerExecutionFill.broker_account_id == partition.broker_account_id,
                BrokerExecutionFill.symbol == partition.symbol,
                BrokerExecutionFill.asset_type == partition.asset_type,
                BrokerExecutionFill.is_active.is_(True),
            )
            .order_by(
                BrokerExecutionFill.execution_time_utc.asc(),
                BrokerExecutionFill.external_execution_id.asc(),
                BrokerExecutionFill.id.asc(),
            )
        )
        if effective_boundary is not None:
            stmt = stmt.where(BrokerExecutionFill.execution_time_utc >= effective_boundary)
        rows = list((await self.db.execute(stmt)).scalars().all())
        return [
            CanonicalExecutionRow(
                canonical_execution_fill_id=row.id,
                external_execution_id=row.external_execution_id,
                symbol=row.symbol,
                side=row.side,
                quantity=row.quantity,
                price=row.price,
                execution_time_utc=row.execution_time_utc,
            )
            for row in rows
        ]

    async def _insert_lifecycles(
        self,
        *,
        state: TradeLifecycleProjectionState,
        partition: LifecycleProjectionPartition,
        generation: int,
        lifecycles,
        boundary: datetime | None,
    ) -> tuple[int, int]:
        existing_count_stmt = select(func.count()).select_from(TradeLifecycleProjection).where(
            TradeLifecycleProjection.tenant_id == partition.tenant_id,
            TradeLifecycleProjection.source == partition.source,
            TradeLifecycleProjection.broker_account_id == partition.broker_account_id,
            TradeLifecycleProjection.symbol == partition.symbol,
            TradeLifecycleProjection.asset_type == partition.asset_type,
        )
        if boundary is not None:
            existing_count_stmt = existing_count_stmt.where(TradeLifecycleProjection.opened_at < boundary)
        existing_count = int((await self.db.execute(existing_count_stmt)).scalar_one())

        lifecycle_rows: list[TradeLifecycleProjection] = []
        allocation_count = 0
        for offset, lifecycle in enumerate(lifecycles, start=1):
            lifecycle_row = TradeLifecycleProjection(
                tenant_id=partition.tenant_id,
                projection_state_id=state.id,
                source=partition.source,
                broker_account_id=partition.broker_account_id,
                symbol=partition.symbol,
                asset_type=partition.asset_type,
                projection_version=PROJECTION_VERSION,
                projection_generation=generation,
                lifecycle_seq=existing_count + offset,
                direction=lifecycle.direction,
                status=lifecycle.status,
                opened_at=lifecycle.opened_at,
                closed_at=lifecycle.closed_at,
                entry_quantity=lifecycle.entry_quantity,
                exit_quantity=lifecycle.exit_quantity,
                remaining_quantity=lifecycle.remaining_quantity,
                avg_entry_price=lifecycle.avg_entry_price,
                avg_exit_price=lifecycle.avg_exit_price,
                realized_pnl=lifecycle.realized_pnl,
            )
            self.db.add(lifecycle_row)
            await self.db.flush()
            for allocation_seq, allocation in enumerate(lifecycle.allocations, start=1):
                self.db.add(
                    TradeLifecycleExecutionAllocation(
                        tenant_id=partition.tenant_id,
                        trade_lifecycle_id=lifecycle_row.id,
                        canonical_execution_fill_id=allocation.canonical_execution_fill_id,
                        projection_version=PROJECTION_VERSION,
                        projection_generation=generation,
                        allocation_seq=allocation_seq,
                        allocation_role=allocation.allocation_role,
                        allocated_quantity=allocation.allocated_quantity,
                        execution_price=allocation.execution_price,
                        execution_time_utc=allocation.execution_time_utc,
                        is_flip_slice=allocation.is_flip_slice,
                    )
                )
                allocation_count += 1
            lifecycle_rows.append(lifecycle_row)
        await self.db.flush()
        return len(lifecycle_rows), allocation_count


async def _get_or_create_projection_state(
    db: AsyncSession,
    *,
    partition: LifecycleProjectionPartition,
) -> TradeLifecycleProjectionState:
    stmt = select(TradeLifecycleProjectionState).where(
        TradeLifecycleProjectionState.tenant_id == partition.tenant_id,
        TradeLifecycleProjectionState.source == partition.source,
        TradeLifecycleProjectionState.broker_account_id == partition.broker_account_id,
        TradeLifecycleProjectionState.symbol == partition.symbol,
        TradeLifecycleProjectionState.asset_type == partition.asset_type,
    )
    state = (await db.execute(stmt)).scalar_one_or_none()
    if state is not None:
        if state.projection_version != PROJECTION_VERSION:
            state.projection_version = PROJECTION_VERSION
            state.is_dirty = True
            state.earliest_dirty_execution_time_utc = None
        return state

    state = TradeLifecycleProjectionState(
        tenant_id=partition.tenant_id,
        source=partition.source,
        broker_account_id=partition.broker_account_id,
        symbol=partition.symbol,
        asset_type=partition.asset_type,
        projection_version=PROJECTION_VERSION,
        current_generation=0,
        is_dirty=False,
    )
    db.add(state)
    await db.flush()
    return state


async def _prepare_rebuild_transaction(db: AsyncSession) -> None:
    if db.in_transaction():
        return
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    await db.connection(execution_options={"isolation_level": "REPEATABLE READ"})


def iter_partitions(rows: Iterable[TradeLifecycleProjectionState]) -> list[LifecycleProjectionPartition]:
    return [
        LifecycleProjectionPartition(
            tenant_id=row.tenant_id,
            source=row.source,
            broker_account_id=row.broker_account_id,
            symbol=row.symbol,
            asset_type=row.asset_type,
        )
        for row in rows
    ]


@asynccontextmanager
async def _transaction_scope(db: AsyncSession):
    if db.in_transaction():
        yield
        return
    async with db.begin():
        yield
