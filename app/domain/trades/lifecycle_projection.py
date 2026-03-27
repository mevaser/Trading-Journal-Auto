from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


_ZERO = Decimal("0")


@dataclass(frozen=True)
class CanonicalExecutionRow:
    """Canonical execution row used for lifecycle persistence rebuilds."""

    canonical_execution_fill_id: int
    external_execution_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    execution_time_utc: datetime


@dataclass(frozen=True)
class LifecycleAllocationSlice:
    """A quantity slice from one canonical execution into one lifecycle."""

    canonical_execution_fill_id: int
    external_execution_id: str
    allocation_role: str
    allocated_quantity: Decimal
    execution_price: Decimal
    execution_time_utc: datetime
    is_flip_slice: bool = False


@dataclass(frozen=True)
class PersistedLifecycle:
    """Lifecycle projection header and ordered allocation slices."""

    symbol: str
    direction: str
    status: str
    opened_at: datetime
    closed_at: datetime | None
    entry_quantity: Decimal
    exit_quantity: Decimal
    remaining_quantity: Decimal
    avg_entry_price: Decimal
    avg_exit_price: Decimal | None
    realized_pnl: Decimal | None
    allocations: list[LifecycleAllocationSlice] = field(default_factory=list)


@dataclass
class _ActiveLifecycle:
    symbol: str
    direction: str
    opened_at: datetime
    entry_allocations: list[LifecycleAllocationSlice]
    exit_allocations: list[LifecycleAllocationSlice]
    open_quantity: Decimal


def build_persisted_lifecycles(executions: list[CanonicalExecutionRow]) -> list[PersistedLifecycle]:
    """Build deterministic lifecycle projections from ordered canonical executions."""
    if not executions:
        return []

    ordered = sorted(
        executions,
        key=lambda item: (
            item.execution_time_utc,
            item.external_execution_id,
            item.canonical_execution_fill_id,
        ),
    )
    first_symbol = ordered[0].symbol
    active: _ActiveLifecycle | None = None
    lifecycles: list[PersistedLifecycle] = []

    for execution in ordered:
        if execution.symbol != first_symbol:
            raise ValueError(f"Mixed symbols are not supported in one lifecycle rebuild: {first_symbol!r}")
        if execution.side not in {"BUY", "SELL"}:
            raise ValueError(f"Unsupported execution side: {execution.side!r}")
        if execution.quantity <= _ZERO:
            raise ValueError(
                f"Execution quantity must be > 0 for canonical_execution_fill_id={execution.canonical_execution_fill_id}"
            )

        if active is None:
            active = _open_new_lifecycle(execution)
            continue

        entry_side = "BUY" if active.direction == "LONG" else "SELL"
        exit_side = "SELL" if active.direction == "LONG" else "BUY"

        if execution.side == entry_side:
            active.entry_allocations.append(
                LifecycleAllocationSlice(
                    canonical_execution_fill_id=execution.canonical_execution_fill_id,
                    external_execution_id=execution.external_execution_id,
                    allocation_role="ENTRY",
                    allocated_quantity=execution.quantity,
                    execution_price=execution.price,
                    execution_time_utc=execution.execution_time_utc,
                )
            )
            active.open_quantity += execution.quantity
            continue

        if execution.side != exit_side:
            raise ValueError(f"Unsupported execution side: {execution.side!r}")

        if execution.quantity <= active.open_quantity:
            active.exit_allocations.append(
                LifecycleAllocationSlice(
                    canonical_execution_fill_id=execution.canonical_execution_fill_id,
                    external_execution_id=execution.external_execution_id,
                    allocation_role="EXIT",
                    allocated_quantity=execution.quantity,
                    execution_price=execution.price,
                    execution_time_utc=execution.execution_time_utc,
                )
            )
            active.open_quantity -= execution.quantity
            if active.open_quantity == _ZERO:
                lifecycles.append(_finalize_lifecycle(active, closed_at=execution.execution_time_utc, status="CLOSED"))
                active = None
            continue

        closing_quantity = active.open_quantity
        remaining_quantity = execution.quantity - closing_quantity
        active.exit_allocations.append(
            LifecycleAllocationSlice(
                canonical_execution_fill_id=execution.canonical_execution_fill_id,
                external_execution_id=execution.external_execution_id,
                allocation_role="EXIT",
                allocated_quantity=closing_quantity,
                execution_price=execution.price,
                execution_time_utc=execution.execution_time_utc,
                is_flip_slice=True,
            )
        )
        active.open_quantity = _ZERO
        lifecycles.append(_finalize_lifecycle(active, closed_at=execution.execution_time_utc, status="CLOSED"))

        flipped_side = "LONG" if active.direction == "SHORT" else "SHORT"
        active = _ActiveLifecycle(
            symbol=execution.symbol,
            direction=flipped_side,
            opened_at=execution.execution_time_utc,
            entry_allocations=[
                LifecycleAllocationSlice(
                    canonical_execution_fill_id=execution.canonical_execution_fill_id,
                    external_execution_id=execution.external_execution_id,
                    allocation_role="ENTRY",
                    allocated_quantity=remaining_quantity,
                    execution_price=execution.price,
                    execution_time_utc=execution.execution_time_utc,
                    is_flip_slice=True,
                )
            ],
            exit_allocations=[],
            open_quantity=remaining_quantity,
        )

    if active is not None:
        lifecycles.append(_finalize_lifecycle(active, closed_at=None, status="OPEN"))

    return lifecycles


def _open_new_lifecycle(execution: CanonicalExecutionRow) -> _ActiveLifecycle:
    direction = "LONG" if execution.side == "BUY" else "SHORT"
    return _ActiveLifecycle(
        symbol=execution.symbol,
        direction=direction,
        opened_at=execution.execution_time_utc,
        entry_allocations=[
            LifecycleAllocationSlice(
                canonical_execution_fill_id=execution.canonical_execution_fill_id,
                external_execution_id=execution.external_execution_id,
                allocation_role="ENTRY",
                allocated_quantity=execution.quantity,
                execution_price=execution.price,
                execution_time_utc=execution.execution_time_utc,
            )
        ],
        exit_allocations=[],
        open_quantity=execution.quantity,
    )


def _finalize_lifecycle(
    active: _ActiveLifecycle,
    *,
    closed_at: datetime | None,
    status: str,
) -> PersistedLifecycle:
    entry_quantity = sum((item.allocated_quantity for item in active.entry_allocations), start=_ZERO)
    exit_quantity = sum((item.allocated_quantity for item in active.exit_allocations), start=_ZERO)
    remaining_quantity = entry_quantity - exit_quantity
    avg_entry_price = _weighted_avg(active.entry_allocations)
    avg_exit_price = _weighted_avg(active.exit_allocations) if active.exit_allocations else None
    realized_pnl = (
        None
        if not active.exit_allocations
        else _realized_pnl(direction=active.direction, avg_entry_price=avg_entry_price, exits=active.exit_allocations)
    )
    return PersistedLifecycle(
        symbol=active.symbol,
        direction=active.direction,
        status=status,
        opened_at=active.opened_at,
        closed_at=closed_at,
        entry_quantity=entry_quantity,
        exit_quantity=exit_quantity,
        remaining_quantity=remaining_quantity,
        avg_entry_price=avg_entry_price,
        avg_exit_price=avg_exit_price,
        realized_pnl=realized_pnl,
        allocations=[*active.entry_allocations, *active.exit_allocations],
    )


def _weighted_avg(allocations: list[LifecycleAllocationSlice]) -> Decimal:
    quantity = sum((item.allocated_quantity for item in allocations), start=_ZERO)
    if quantity == _ZERO:
        return _ZERO
    notional = sum((item.allocated_quantity * item.execution_price for item in allocations), start=_ZERO)
    return notional / quantity


def _realized_pnl(
    *,
    direction: str,
    avg_entry_price: Decimal,
    exits: list[LifecycleAllocationSlice],
) -> Decimal:
    pnl = _ZERO
    for item in exits:
        if direction == "LONG":
            pnl += (item.execution_price - avg_entry_price) * item.allocated_quantity
            continue
        if direction == "SHORT":
            pnl += (avg_entry_price - item.execution_price) * item.allocated_quantity
            continue
        raise ValueError(f"Unsupported lifecycle direction: {direction!r}")
    return pnl
