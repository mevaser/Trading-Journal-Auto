from __future__ import annotations

from enum import Enum


class TradeDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeStatus(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
