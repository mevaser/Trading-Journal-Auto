from __future__ import annotations

from dataclasses import dataclass

from app.domain.executions.models import ExecutionDTO
from app.domain.trades.lifecycle_models import TradeLifecycle
from app.domain.trades.lifecycle_services import build_trade_lifecycles


@dataclass(frozen=True)
class LifecycleBatchResult:
    """Batch lifecycle reconstruction result with per-symbol failure isolation."""

    lifecycles: list[TradeLifecycle]
    failed: list[str]


def build_lifecycle_batch(executions: list[ExecutionDTO]) -> LifecycleBatchResult:
    """Build lifecycles per symbol and continue processing when one symbol fails."""
    by_symbol: dict[str, list[ExecutionDTO]] = {}
    for execution in executions:
        by_symbol.setdefault(execution.symbol, []).append(execution)

    lifecycles: list[TradeLifecycle] = []
    failed: list[str] = []

    for symbol, symbol_executions in by_symbol.items():
        ordered = sorted(symbol_executions, key=lambda item: (item.execution_time, item.exec_id))
        try:
            lifecycles.extend(build_trade_lifecycles(ordered))
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{symbol}: {exc}")

    return LifecycleBatchResult(lifecycles=lifecycles, failed=failed)
