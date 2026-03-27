from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.executions.models import ExecutionDTO


@dataclass(frozen=True)
class Trade:
    """Temporary same-day single-leg aggregation, not the final trade lifecycle model."""

    symbol: str
    side: str
    trade_date: date
    quantity: float
    avg_price: float
    executions: list[ExecutionDTO]
