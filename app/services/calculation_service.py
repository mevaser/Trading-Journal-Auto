from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from app.db.models import Trade, TradeFill


ZERO = Decimal("0")


@dataclass
class TradeMetrics:
    opened_at: datetime | None
    closed_at: datetime | None
    avg_entry_price: Decimal | None
    avg_exit_price: Decimal | None
    quantity_opened: Decimal
    quantity_closed: Decimal
    remaining_quantity: Decimal
    pnl_usd: Decimal | None
    pnl_pct: Decimal | None
    status: str
    is_intraday: bool | None
    duration_days: int | None


def _weighted_avg(total_notional: Decimal, total_qty: Decimal) -> Decimal | None:
    if total_qty <= ZERO:
        return None
    return total_notional / total_qty


def calculate_trade_metrics(trade: Trade, fills: Iterable[TradeFill]) -> TradeMetrics:
    direction = trade.direction.upper()
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")

    opening_side = "BUY" if direction == "LONG" else "SELL"
    closing_side = "SELL" if direction == "LONG" else "BUY"

    ordered_fills = sorted(fills, key=lambda item: item.fill_datetime)

    open_qty = ZERO
    close_qty = ZERO
    open_notional = ZERO
    close_notional = ZERO
    total_commission = ZERO

    opening_timestamps: list[datetime] = []
    closing_timestamps: list[datetime] = []

    for fill in ordered_fills:
        side = fill.side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("fill side must be BUY or SELL")

        qty = Decimal(fill.quantity)
        price = Decimal(fill.price)
        commission = Decimal(fill.commission or ZERO)

        total_commission += commission
        if side == opening_side:
            open_qty += qty
            open_notional += qty * price
            opening_timestamps.append(fill.fill_datetime)
        elif side == closing_side:
            close_qty += qty
            close_notional += qty * price
            closing_timestamps.append(fill.fill_datetime)

    if close_qty > open_qty:
        raise ValueError("closing quantity cannot exceed opened quantity")

    avg_entry = _weighted_avg(open_notional, open_qty)
    avg_exit = _weighted_avg(close_notional, close_qty)

    remaining = open_qty - close_qty

    if open_qty == ZERO:
        status = "open"
    elif remaining == ZERO:
        status = "closed"
    elif close_qty > ZERO:
        status = "partial"
    else:
        status = "open"

    realized_qty = close_qty
    pnl_usd: Decimal | None = None
    pnl_pct: Decimal | None = None

    if realized_qty > ZERO and avg_entry is not None and avg_exit is not None:
        gross_pnl = (
            (avg_exit - avg_entry) * realized_qty
            if direction == "LONG"
            else (avg_entry - avg_exit) * realized_qty
        )
        pnl_usd = gross_pnl - total_commission

        cost_basis = avg_entry * realized_qty
        if cost_basis > ZERO:
            pnl_pct = (pnl_usd / cost_basis) * Decimal("100")

    opened_at = min(opening_timestamps) if opening_timestamps else None
    closed_at = max(closing_timestamps) if status == "closed" and closing_timestamps else None
    is_intraday = None
    duration_days = None

    if opened_at and closed_at:
        is_intraday = opened_at.date() == closed_at.date()
        duration_days = (closed_at.date() - opened_at.date()).days

    return TradeMetrics(
        opened_at=opened_at,
        closed_at=closed_at,
        avg_entry_price=avg_entry,
        avg_exit_price=avg_exit,
        quantity_opened=open_qty,
        quantity_closed=close_qty,
        remaining_quantity=remaining,
        pnl_usd=pnl_usd,
        pnl_pct=pnl_pct,
        status=status,
        is_intraday=is_intraday,
        duration_days=duration_days,
    )
