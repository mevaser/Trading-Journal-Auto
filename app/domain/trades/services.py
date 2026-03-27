from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.domain.executions.models import ExecutionDTO
from app.domain.trades.models import Trade


def build_trades_from_executions(executions: list[ExecutionDTO]) -> list[Trade]:
    """Build temporary same-day single-leg trade aggregates from execution rows."""
    grouped: dict[tuple[str, str, date], list[ExecutionDTO]] = defaultdict(list)
    for execution in executions:
        grouped[(execution.symbol, execution.side, execution.execution_time.date())].append(execution)

    trades: list[Trade] = []
    for (symbol, side, trade_date), rows in grouped.items():
        quantity = sum(row.quantity for row in rows)
        notional = sum(row.quantity * row.price for row in rows)
        avg_price = notional / quantity if quantity > 0 else 0.0
        trades.append(
            Trade(
                symbol=symbol,
                side=side,
                trade_date=trade_date,
                quantity=quantity,
                avg_price=avg_price,
                executions=list(rows),
            )
        )

    return trades
