from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TradeResolutionAction(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


@dataclass
class TradeResolutionResult:
    action: TradeResolutionAction
    trade_id: int | None
    fill_id: int | None
    reason: str | None = None
