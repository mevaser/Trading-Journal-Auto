from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class ExecutionSide(StrEnum):
    """Normalized execution side values."""

    BUY = "BUY"
    SELL = "SELL"


class AssetType(StrEnum):
    """Minimal V1 asset classes for normalized broker executions."""

    STOCK = "stock"
    OPTION = "option"
    FUTURE = "future"
    FOREX = "forex"
    CRYPTO = "crypto"
    OTHER = "other"


@dataclass(slots=True)
class ExecutionDTO:
    """Normalized broker execution payload used across adapters."""

    external_execution_id: str
    symbol: str
    side: ExecutionSide
    asset_type: AssetType
    quantity: Decimal
    price: Decimal
    execution_time: datetime
    commission: Decimal | None = None
    currency: str | None = None
    account_id: str | None = None

    def __post_init__(self) -> None:
        """Enforce a timezone-aware UTC execution timestamp contract."""
        if self.execution_time.tzinfo is None:
            raise ValueError("execution_time must be timezone-aware")
        self.execution_time = self.execution_time.astimezone(UTC)
