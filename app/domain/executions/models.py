from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExecutionDTO:
    """Normalized execution payload used by domain-level workflows."""

    exec_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    account: str
    execution_time: datetime
