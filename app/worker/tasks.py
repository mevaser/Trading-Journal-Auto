from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.api.import_schemas import ExecutionImportPayload
from app.db.models import ImportRun, JobRun
from app.db.session import AsyncSessionLocal
from app.services.import_orchestrator import parse_iso_utc, run_import_sync
from app.worker.celery_app import celery_app


@celery_app.task(name="worker.ping")
def ping() -> dict[str, str]:
    """Small health task used to validate worker wiring."""
    return {"status": "ok"}


@celery_app.task(bind=True, name="worker.import_ibkr_executions")
def import_ibkr_executions(
    self,
    *,
    import_run_id: int,
    tenant_id: int,
    user_id: int | None,
    start_time: str,
    end_time: str,
    account_ref: str | None,
    broker_account_id: str | None,
    source: str,
    inline_executions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Run IBKR import in background and persist run/job status."""
    return asyncio.run(
        _run_import_task(
            task_id=self.request.id,
            import_run_id=import_run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            account_ref=account_ref,
            broker_account_id=broker_account_id,
            source=source,
            inline_executions=inline_executions,
        )
    )


async def _run_import_task(
    *,
    task_id: str,
    import_run_id: int,
    tenant_id: int,
    user_id: int | None,
    start_time: str,
    end_time: str,
    account_ref: str | None,
    broker_account_id: str | None,
    source: str,
    inline_executions: list[dict[str, object]] | None,
) -> dict[str, object]:
    async with AsyncSessionLocal() as db:
        job = (
            await db.execute(
                select(JobRun).where(
                    JobRun.external_job_id == task_id,
                    JobRun.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if job is not None:
            job.status = "running"
            job.started_at = datetime.now(UTC)

        run = (
            await db.execute(
                select(ImportRun).where(
                    ImportRun.id == import_run_id,
                    ImportRun.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if run is None:
            if job is not None:
                job.status = "failed"
                job.error_message = f"Import run {import_run_id} not found"
                job.finished_at = datetime.now(UTC)
                await db.commit()
            return {"status": "failed", "error": "import run not found"}

        executions = (
            [ExecutionImportPayload.model_validate(item) for item in inline_executions]
            if inline_executions
            else None
        )

        try:
            updated_run, summary = await run_import_sync(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                start_time=parse_iso_utc(start_time),
                end_time=parse_iso_utc(end_time),
                account_ref=account_ref,
                broker_account_id=broker_account_id,
                source=source,
                inline_executions=executions,
                import_run=run,
            )
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.completed_at = datetime.now(UTC)
            run.error_count = 1
            run.error_details = json.dumps([str(exc)])

            if job is not None:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = datetime.now(UTC)
            await db.commit()
            return {"status": "failed", "error": str(exc)}

        if job is not None:
            job.status = "completed"
            job.finished_at = datetime.now(UTC)
            job.result_json = summary.to_json()
            await db.commit()

        return {
            "status": "completed",
            "import_run_id": updated_run.id,
            "summary": json.loads(summary.to_json()),
        }
