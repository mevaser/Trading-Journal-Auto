from __future__ import annotations

from dataclasses import dataclass, field

from app.brokers.ibkr.dto import ExecutionDTO


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

                trade_action = await self._resolve_trade_for_execution(execution)
                if trade_action == "created":
                    summary.trades_created += 1
                elif trade_action == "updated":
                    summary.trades_updated += 1

                await self._insert_fill_from_execution(execution)
                summary.imported += 1
            except Exception as exc:  # noqa: BLE001 - keep skeleton resilient for batch import.
                summary.failed += 1
                summary.errors.append(
                    f"execution_id={execution.external_execution_id}: {exc}"
                )

        return summary

    async def _is_duplicate_execution(self, execution: ExecutionDTO) -> bool:
        """Placeholder for future duplicate detection by external execution id."""
        _ = execution
        return False

    async def _resolve_trade_for_execution(self, execution: ExecutionDTO) -> str:
        """Placeholder for future trade matching/creation strategy."""
        _ = execution
        return "unchanged"

    async def _insert_fill_from_execution(self, execution: ExecutionDTO) -> None:
        """Placeholder for future fill insertion into persistence layer."""
        _ = execution
