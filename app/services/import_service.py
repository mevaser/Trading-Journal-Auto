from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.brokers.ibkr.dto import AssetType, ExecutionDTO


@dataclass(slots=True)
class ImportSummary:
    """Aggregate import result for a single execution batch."""

    total_received: int = 0
    imported: int = 0
    duplicates_skipped: int = 0
    failed: int = 0
    trades_created: int = 0
    trades_updated: int = 0
    errors: list[str] = field(default_factory=list)


class TradeResolutionAction(StrEnum):
    """Trade resolution outcome for an execution."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


@dataclass(slots=True)
class TradeResolutionResult:
    """Resolved trade context required for downstream fill insertion."""

    action: TradeResolutionAction
    trade_id: int | None
    symbol: str
    asset_type: AssetType
    user_id: int | None = None


class TradeImportService:
    """Imports normalized broker executions into the journal domain."""

    async def import_executions(self, executions: list[ExecutionDTO]) -> ImportSummary:
        """Process executions and return a summary of import outcomes."""
        summary = ImportSummary(total_received=len(executions))

        for execution in executions:
            try:
                if await self._is_duplicate_execution(execution):
                    summary.duplicates_skipped += 1
                    continue

                resolution = await self._resolve_trade_for_execution(execution)
                if resolution.action == TradeResolutionAction.CREATED:
                    summary.trades_created += 1
                elif resolution.action == TradeResolutionAction.UPDATED:
                    summary.trades_updated += 1

                await self._insert_fill_from_execution(execution, resolution)
                summary.imported += 1
            except Exception as exc:  # noqa: BLE001 - keep skeleton resilient for batch import.
                summary.failed += 1
                summary.errors.append(
                    f"external_execution_id={execution.external_execution_id}: {exc}"
                )

        return summary

    async def _is_duplicate_execution(self, execution: ExecutionDTO) -> bool:
        """Placeholder for future duplicate detection by external execution id."""
        _ = execution
        return False

    async def _resolve_trade_for_execution(
        self, execution: ExecutionDTO
    ) -> TradeResolutionResult:
        """Placeholder for future trade matching/creation strategy."""
        return TradeResolutionResult(
            action=TradeResolutionAction.UNCHANGED,
            trade_id=None,
            symbol=execution.symbol,
            asset_type=execution.asset_type,
            user_id=None,
        )

    async def _insert_fill_from_execution(
        self, execution: ExecutionDTO, resolution: TradeResolutionResult
    ) -> None:
        """Placeholder for future fill insertion into persistence layer."""
        _ = execution, resolution
