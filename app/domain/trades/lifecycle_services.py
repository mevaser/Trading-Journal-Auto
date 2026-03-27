from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from app.domain.executions.models import ExecutionDTO
from app.domain.trades.enums import TradeDirection, TradeStatus
from app.domain.trades.lifecycle_models import TradeLifecycle

_EPSILON = 1e-9


@dataclass
class _ActiveLifecycle:
    symbol: str
    direction: TradeDirection
    entry_fills: list[ExecutionDTO]
    exit_fills: list[ExecutionDTO]
    open_quantity: float
    opened_at: datetime


def build_trade_lifecycles(executions: list[ExecutionDTO]) -> list[TradeLifecycle]:
    """Build lifecycle trades from single-symbol execution rows."""
    ordered_executions = sorted(executions, key=lambda item: (item.execution_time, item.exec_id))
    if not ordered_executions:
        return []

    first_symbol = ordered_executions[0].symbol
    lifecycles: list[TradeLifecycle] = []
    active: _ActiveLifecycle | None = None

    for execution in ordered_executions:
        if execution.symbol != first_symbol:
            raise ValueError(
                f"Mixed symbols are not supported in one call: {first_symbol!r} and {execution.symbol!r}"
            )
        if execution.side not in {"BUY", "SELL"}:
            raise ValueError(f"Unsupported execution side: {execution.side!r}")
        if execution.quantity <= 0:
            raise ValueError(f"Execution quantity must be > 0 for exec_id={execution.exec_id!r}")

        if active is None:
            direction = TradeDirection.LONG if execution.side == "BUY" else TradeDirection.SHORT
            active = _ActiveLifecycle(
                symbol=execution.symbol,
                direction=direction,
                entry_fills=[execution],
                exit_fills=[],
                open_quantity=execution.quantity,
                opened_at=execution.execution_time,
            )
            continue

        entry_side = "BUY" if active.direction == TradeDirection.LONG else "SELL"
        exit_side = "SELL" if active.direction == TradeDirection.LONG else "BUY"

        if execution.side == entry_side:
            active.entry_fills.append(execution)
            active.open_quantity += execution.quantity
            continue

        if execution.side != exit_side:
            raise ValueError(f"Unsupported execution side: {execution.side!r}")

        if execution.quantity <= active.open_quantity + _EPSILON:
            active.exit_fills.append(execution)
            active.open_quantity -= execution.quantity
            if abs(active.open_quantity) <= _EPSILON:
                active.open_quantity = 0.0

            if active.open_quantity == 0.0:
                lifecycles.append(
                    TradeLifecycle(
                        symbol=active.symbol,
                        direction=active.direction,
                        entry_fills=list(active.entry_fills),
                        exit_fills=list(active.exit_fills),
                        open_quantity=0.0,
                        opened_at=active.opened_at,
                        closed_at=execution.execution_time,
                        status=TradeStatus.CLOSED,
                    )
                )
                active = None
            continue

        closing_quantity = active.open_quantity
        remaining_quantity = execution.quantity - closing_quantity

        closing_part = _with_quantity(execution, closing_quantity)
        active.exit_fills.append(closing_part)
        active.open_quantity = 0.0
        lifecycles.append(
            TradeLifecycle(
                symbol=active.symbol,
                direction=active.direction,
                entry_fills=list(active.entry_fills),
                exit_fills=list(active.exit_fills),
                open_quantity=0.0,
                opened_at=active.opened_at,
                closed_at=execution.execution_time,
                status=TradeStatus.CLOSED,
            )
        )

        flipped_direction = (
            TradeDirection.SHORT if active.direction == TradeDirection.LONG else TradeDirection.LONG
        )
        opening_part = _with_quantity(execution, remaining_quantity)
        active = _ActiveLifecycle(
            symbol=execution.symbol,
            direction=flipped_direction,
            entry_fills=[opening_part],
            exit_fills=[],
            open_quantity=remaining_quantity,
            opened_at=execution.execution_time,
        )

    if active is not None:
        lifecycles.append(
            TradeLifecycle(
                symbol=active.symbol,
                direction=active.direction,
                entry_fills=list(active.entry_fills),
                exit_fills=list(active.exit_fills),
                open_quantity=active.open_quantity,
                opened_at=active.opened_at,
                closed_at=None,
                status=TradeStatus.OPEN,
            )
        )

    return lifecycles


def _with_quantity(execution: ExecutionDTO, quantity: float) -> ExecutionDTO:
    """Return a logical execution slice that preserves metadata and updates quantity."""
    return replace(execution, quantity=quantity)
