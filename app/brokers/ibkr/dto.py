from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class ExecutionDTO:
    """Normalized broker execution payload used across adapters."""

    external_execution_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    execution_time: datetime
    commission: Decimal | None = None
    currency: str | None = None
    account_id: str | None = None
