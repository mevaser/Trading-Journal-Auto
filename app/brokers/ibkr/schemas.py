from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPreview:
    """Minimal execution payload used for IBKR preview responses."""

    exec_id: str
    symbol: str | None
    side: str | None
    shares: float | None
    price: float | None
    account: str | None
    execution_time: str | None
