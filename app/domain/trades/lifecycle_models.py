from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.executions.models import ExecutionDTO
from app.domain.trades.enums import TradeDirection, TradeStatus


@dataclass(frozen=True)
class OpenLot:
    """Represents an open entry lot in a lifecycle trade state."""

    quantity: float
    price: float
    execution_time: datetime
    execution_id: str


@dataclass(frozen=True)
class ExitFill:
    """Represents an exit fill applied against an existing lifecycle position."""

    quantity: float
    price: float
    execution_time: datetime
    execution_id: str


@dataclass(frozen=True)
class TradeLifecycle:
    """Lifecycle-based trade state for positions with partial exits across multiple days.

    This model tracks a full trade lifecycle rather than same-day aggregation and is intended
    to replace the temporary same-day trade model in a later step.
    LONG opens with BUY entry fills and closes with SELL exit fills.
    SHORT opens with SELL entry fills and closes with BUY exit fills.
    """

    symbol: str
    direction: TradeDirection
    entry_fills: list[ExecutionDTO]
    exit_fills: list[ExecutionDTO]
    open_quantity: float
    opened_at: datetime
    closed_at: datetime | None
    status: TradeStatus
    avg_entry_price: float = field(init=False)
    avg_exit_price: float | None = field(init=False)
    realized_pnl: float | None = field(init=False)

    def __post_init__(self) -> None:
        """Compute weighted-average pricing metrics and realized PnL from fills."""
        avg_entry_price = _weighted_avg_price(self.entry_fills)
        avg_exit_price = _weighted_avg_price(self.exit_fills) if self.exit_fills else None
        realized_pnl = (
            None
            if not self.exit_fills
            else _calculate_realized_pnl(
                direction=self.direction,
                avg_entry_price=avg_entry_price,
                exit_fills=self.exit_fills,
            )
        )
        object.__setattr__(self, "avg_entry_price", avg_entry_price)
        object.__setattr__(self, "avg_exit_price", avg_exit_price)
        object.__setattr__(self, "realized_pnl", realized_pnl)


def _weighted_avg_price(fills: list[ExecutionDTO]) -> float:
    quantity = sum(fill.quantity for fill in fills)
    if quantity <= 0:
        return 0.0
    notional = sum(fill.quantity * fill.price for fill in fills)
    return notional / quantity


def _calculate_realized_pnl(
    *,
    direction: TradeDirection,
    avg_entry_price: float,
    exit_fills: list[ExecutionDTO],
) -> float:
    pnl = 0.0
    for fill in exit_fills:
        if direction == TradeDirection.LONG:
            pnl += (fill.price - avg_entry_price) * fill.quantity
        elif direction == TradeDirection.SHORT:
            pnl += (avg_entry_price - fill.price) * fill.quantity
        else:
            raise ValueError(f"Unsupported trade direction: {direction!r}")
    return pnl
