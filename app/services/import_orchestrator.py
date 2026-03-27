from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.import_schemas import ExecutionImportPayload, utc_now
from app.brokers.ibkr.dto import ExecutionDTO
from app.brokers.ibkr.ib_insync_adapter import IBInsyncIBKRAdapter
from app.db.models import ImportRun, JobRun
from app.observability import DomainValidationError, ResourceNotFoundError
from app.services.import_service import ImportSummary, TradeImportService


async def create_import_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int | None,
    source: str,
    broker_account_id: str | None,
    window_start: datetime,
    window_end: datetime,
) -> ImportRun:
    run = ImportRun(
        tenant_id=tenant_id,
        user_id=user_id,
        source=source,
        broker_account_id=broker_account_id,
        status="pending",
        window_start=window_start,
        window_end=window_end,
    )
    db.add(run)
    await db.flush()
    return run


async def run_import_sync(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int | None,
    start_time: datetime,
    end_time: datetime,
    account_ref: str | None,
    broker_account_id: str | None,
    source: str = "ibkr",
    inline_executions: list[ExecutionImportPayload] | None = None,
    import_run: ImportRun | None = None,
) -> tuple[ImportRun, ImportSummary]:
    if end_time <= start_time:
        raise DomainValidationError("end_time must be greater than start_time")

    if import_run is None:
        import_run = await create_import_run(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            source=source,
            broker_account_id=broker_account_id,
            window_start=start_time,
            window_end=end_time,
        )
    else:
        import_run.window_start = start_time
        import_run.window_end = end_time
        import_run.source = source
        import_run.broker_account_id = broker_account_id
    import_run.status = "running"
    import_run.started_at = utc_now()

    executions = await load_executions(
        start_time=start_time,
        end_time=end_time,
        account_ref=account_ref,
        inline_executions=inline_executions,
    )
    importer = TradeImportService(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        source=source,
        broker_account_id=broker_account_id or account_ref,
    )
    summary = await importer.import_executions(executions, import_run=import_run)
    import_run.completed_at = utc_now()
    if import_run.status not in {"completed", "failed"}:
        import_run.status = "completed"
    await db.commit()
    await db.refresh(import_run)
    return import_run, summary


async def load_executions(
    *,
    start_time: datetime,
    end_time: datetime,
    account_ref: str | None,
    inline_executions: list[ExecutionImportPayload] | None,
) -> list[ExecutionDTO]:
    if inline_executions:
        return [item.to_dto() for item in inline_executions]

    adapter = IBInsyncIBKRAdapter(
        host=os.getenv("IBKR_HOST", "127.0.0.1"),
        port=int(os.getenv("IBKR_PORT", "7497")),
        client_id=int(os.getenv("IBKR_CLIENT_ID", "19")),
    )
    return await adapter.fetch_executions(start_time=start_time, end_time=end_time, account_ref=account_ref)


async def create_job_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int | None,
    import_run_id: int,
    external_job_id: str,
    payload: dict[str, object],
) -> JobRun:
    job = JobRun(
        tenant_id=tenant_id,
        user_id=user_id,
        import_run_id=import_run_id,
        external_job_id=external_job_id,
        status="queued",
        payload_json=json.dumps(payload),
    )
    db.add(job)
    await db.flush()
    return job


async def get_import_run_or_404(db: AsyncSession, *, run_id: int, tenant_id: int) -> ImportRun:
    stmt = select(ImportRun).where(and_(ImportRun.id == run_id, ImportRun.tenant_id == tenant_id))
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise ResourceNotFoundError("Import run not found", details={"run_id": run_id})
    return run


async def list_import_runs(db: AsyncSession, *, tenant_id: int, limit: int = 50) -> list[ImportRun]:
    stmt = (
        select(ImportRun)
        .where(ImportRun.tenant_id == tenant_id)
        .order_by(ImportRun.created_at.desc(), ImportRun.id.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_job_run_or_404(db: AsyncSession, *, external_job_id: str, tenant_id: int) -> JobRun:
    stmt = select(JobRun).where(
        and_(
            JobRun.external_job_id == external_job_id,
            JobRun.tenant_id == tenant_id,
        )
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError("Job not found", details={"job_id": external_job_id})
    return job


def parse_iso_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
