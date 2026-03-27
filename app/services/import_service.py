from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.ibkr.dto import ExecutionDTO
from app.db.models import BrokerExecutionFill, ImportRun, TradeFill
from app.observability import get_logger
from app.services.execution_ingestion import process_staged_record, stage_records
from app.services.projection_service import ProjectionService
from app.services.trade_resolver import TradeResolver


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

    def to_json(self) -> str:
        return json.dumps(
            {
                "total_received": self.total_received,
                "imported": self.imported,
                "duplicates_skipped": self.duplicates_skipped,
                "failed": self.failed,
                "trades_created": self.trades_created,
                "trades_updated": self.trades_updated,
                "errors": self.errors,
            }
        )


projection_logger = get_logger("app.import.projection")


class TradeImportService:
    """Stage 1 import service: canonical execution ingestion only."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        user_id: int | None,
        source: str = "ibkr",
        broker_account_id: str | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.source = source.strip().lower() or "ibkr"
        self.broker_account_id = (broker_account_id or "").strip() or None

    async def import_executions(
        self,
        executions: list[ExecutionDTO],
        *,
        import_run: ImportRun | None = None,
    ) -> ImportSummary:
        summary = ImportSummary()
        if import_run is not None:
            import_run.status = "running"

        if import_run is None:
            raise ValueError("import_run is required for Stage 1 ingestion")

        staged_records = await stage_records(
            self.db,
            import_run=import_run,
            tenant_id=self.tenant_id,
            source=self.source,
            default_broker_account_id=self.broker_account_id,
            executions=executions,
        )
        summary.total_received = len(staged_records)
        resolver = TradeResolver()
        projection = ProjectionService()

        for record in staged_records:
            try:
                async with self.db.begin_nested():
                    final_status = await process_staged_record(
                        self.db,
                        record=record,
                        import_run_id=import_run.id,
                    )
            except Exception as exc:  # noqa: BLE001 - continue processing other rows
                record.status = "failed_processing"
                record.error_code = "record_processing_exception"
                record.error_message = str(exc)
                record.resolved_at = datetime.now(UTC)
                await self.db.flush()
                final_status = record.status

            if final_status == "resolved_inserted":
                execution = executions[record.record_seq - 1]
                try:
                    resolution = await resolver.resolve_execution(
                        execution=execution,
                        session=self.db,
                        tenant_id=self.tenant_id,
                    )
                    await projection.apply_resolution(
                        session=self.db,
                        execution=execution,
                        resolution=resolution,
                        tenant_id=self.tenant_id,
                        user_id=self.user_id if self.user_id is not None else 1,
                        canonical_execution_fill_id=record.canonical_execution_fill_id,
                    )
                except Exception as exc:  # noqa: BLE001 - row-level projection failures must not stop import
                    projection_logger.warning(
                        "projection_failed",
                        extra={
                            "event": "projection_failed",
                            "record_seq": record.record_seq,
                            "external_execution_id": execution.external_execution_id,
                            "canonical_execution_fill_id": record.canonical_execution_fill_id,
                            "tenant_id": self.tenant_id,
                            "error": str(exc),
                        },
                    )
            elif final_status == "resolved_superseded":
                execution = executions[record.record_seq - 1]
                superseded_canonical_id = None
                projected_fill_exists = False
                if record.canonical_execution_fill_id is not None:
                    canonical_fill = await self.db.get(
                        BrokerExecutionFill,
                        record.canonical_execution_fill_id,
                    )
                    if canonical_fill is not None:
                        superseded_canonical_id = canonical_fill.supersedes_execution_fill_id
                if superseded_canonical_id is not None:
                    projected_fill_exists = (
                        await self.db.execute(
                            select(TradeFill.id).where(
                                TradeFill.tenant_id == self.tenant_id,
                                TradeFill.canonical_execution_fill_id == superseded_canonical_id,
                            )
                        )
                    ).scalar_one_or_none() is not None
                projection_logger.warning(
                    "projection_superseded_deferred",
                    extra={
                        "event": "projection_superseded_deferred",
                        "record_seq": record.record_seq,
                        "external_execution_id": execution.external_execution_id,
                        "canonical_execution_fill_id": record.canonical_execution_fill_id,
                        "superseded_canonical_execution_fill_id": superseded_canonical_id,
                        "projected_fill_exists": projected_fill_exists,
                        "tenant_id": self.tenant_id,
                    },
                )

            if final_status in {"resolved_inserted", "resolved_superseded"}:
                summary.imported += 1
            elif final_status == "duplicate_skipped":
                summary.duplicates_skipped += 1
            elif final_status in {"failed_validation", "failed_processing"}:
                summary.failed += 1
                summary.errors.append(
                    f"record_seq={record.record_seq} external_execution_id={record.external_execution_id}: "
                    f"{record.error_message or record.status}"
                )

        _update_import_run_metrics(import_run, summary)
        return summary


def _update_import_run_metrics(import_run: ImportRun, summary: ImportSummary) -> None:
    import_run.total_received = summary.total_received
    import_run.imported = summary.imported
    import_run.duplicates_skipped = summary.duplicates_skipped
    import_run.failed = summary.failed
    import_run.trades_created = 0
    import_run.trades_updated = 0
    import_run.error_count = len(summary.errors)
    import_run.error_details = json.dumps(summary.errors) if summary.errors else None
    import_run.status = "failed" if summary.failed > 0 else "completed"
