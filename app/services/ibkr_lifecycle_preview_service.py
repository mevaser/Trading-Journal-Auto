from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.brokers.ibkr.service import IBKRService
from app.domain.executions.models import ExecutionDTO
from app.domain.trades.lifecycle_batch import build_lifecycle_batch
from app.domain.trades.lifecycle_models import TradeLifecycle


@dataclass(frozen=True)
class IBKRLifecyclePreviewResult:
    """Read-only preview payload with executions and lifecycle-based trade views."""

    executions: list[ExecutionDTO]
    lifecycles: list[TradeLifecycle]
    failed: list[str]


class IBKRLifecyclePreviewService:
    """Application service that composes IBKR execution preview with lifecycle reconstruction."""

    def __init__(self) -> None:
        self._ibkr_service = IBKRService()

    def get_preview(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> IBKRLifecyclePreviewResult:
        """Return normalized executions and lifecycle trades for the requested time window."""
        executions = self._ibkr_service.get_executions_preview(start_time=start_time, end_time=end_time)
        executions = sorted(executions, key=lambda item: (item.execution_time, item.exec_id))
        batch_result = build_lifecycle_batch(executions)
        return IBKRLifecyclePreviewResult(
            executions=executions,
            lifecycles=batch_result.lifecycles,
            failed=batch_result.failed,
        )
