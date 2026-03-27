from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.import_schemas import (
    BrokerImportRequest,
    BrokerImportResponse,
    ImportSummaryResponse,
    utc_now,
)
from app.auth.dependencies import (
    TenantRequestContext,
    get_request_tenant_context,
    require_tenant_context,
)
from app.db.models import ImportRun
from app.db.session import get_db
from app.observability import DomainValidationError
from app.brokers.ibkr.service import IBKRService
from app.services.ibkr_lifecycle_preview_service import IBKRLifecyclePreviewService
from app.services.import_orchestrator import create_job_run, create_import_run, run_import_sync


router = APIRouter(
    prefix="/broker/ibkr",
    tags=["Broker Import"],
    dependencies=[Depends(require_tenant_context)],
)


@router.get("/test-connection")
async def test_ibkr_connection() -> dict[str, str]:
    """Test connectivity to IBKR using the dedicated service layer."""
    service = IBKRService()
    return await asyncio.to_thread(service.test_connection)


@router.get("/executions-preview")
async def get_ibkr_executions_preview(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[dict[str, object | None]]:
    """Return a read-only preview list of IBKR executions for an optional time window."""
    service = IBKRService()
    previews = await asyncio.to_thread(
        service.get_executions_preview,
        start_time,
        end_time,
    )
    previews = sorted(previews, key=lambda item: (item.execution_time, item.exec_id))
    return [
        {
            "exec_id": item.exec_id,
            "symbol": item.symbol,
            "side": item.side,
            "quantity": item.quantity,
            "price": item.price,
            "account": item.account,
            "execution_time": item.execution_time.isoformat(),
        }
        for item in previews
    ]


@router.get("/lifecycle-preview")
async def get_ibkr_lifecycle_preview(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, object]:
    """Return read-only normalized executions and lifecycle trade previews from IBKR."""
    service = IBKRLifecyclePreviewService()
    result = await asyncio.to_thread(
        service.get_preview,
        start_time,
        end_time,
    )
    executions_payload = [
        {
            "exec_id": item.exec_id,
            "symbol": item.symbol,
            "side": item.side,
            "quantity": item.quantity,
            "price": item.price,
            "account": item.account,
            "execution_time": item.execution_time.isoformat(),
        }
        for item in result.executions
    ]
    lifecycles_payload = [
        {
            "symbol": item.symbol,
            "direction": item.direction.value,
            "open_quantity": item.open_quantity,
            "opened_at": item.opened_at.isoformat(),
            "closed_at": item.closed_at.isoformat() if item.closed_at else None,
            "status": item.status.value,
            "avg_entry_price": item.avg_entry_price,
            "avg_exit_price": item.avg_exit_price,
            "realized_pnl": item.realized_pnl,
            "entry_fills_count": len(item.entry_fills),
            "exit_fills_count": len(item.exit_fills),
        }
        for item in result.lifecycles
    ]
    return {
        "executions_count": len(executions_payload),
        "lifecycles_count": len(lifecycles_payload),
        "failed_count": len(result.failed),
        "executions": executions_payload,
        "lifecycles": lifecycles_payload,
        "failed": list(result.failed),
    }


@router.post("/import", response_model=BrokerImportResponse)
async def trigger_ibkr_import(
    payload: BrokerImportRequest,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> BrokerImportResponse:
    source = "ibkr"
    if payload.async_mode:
        import_run = await create_import_run(
            db,
            tenant_id=tenant_ctx.tenant_id,
            user_id=tenant_ctx.user_id,
            source=source,
            broker_account_id=payload.broker_account_id,
            window_start=payload.start_time,
            window_end=payload.end_time,
        )
        import_run.status = "pending"
        import_run.started_at = utc_now()

        task_id = _enqueue_import_job(
            import_run_id=import_run.id,
            tenant_id=tenant_ctx.tenant_id,
            user_id=tenant_ctx.user_id,
            start_time=payload.start_time.isoformat(),
            end_time=payload.end_time.isoformat(),
            account_ref=payload.account_ref,
            broker_account_id=payload.broker_account_id,
            source=source,
            inline_executions=(
                [item.model_dump(mode="json") for item in payload.executions]
                if payload.executions
                else None
            ),
        )
        import_run.job_id = task_id
        await create_job_run(
            db,
            tenant_id=tenant_ctx.tenant_id,
            user_id=tenant_ctx.user_id,
            import_run_id=import_run.id,
            external_job_id=task_id,
            payload={
                "start_time": payload.start_time.isoformat(),
                "end_time": payload.end_time.isoformat(),
                "account_ref": payload.account_ref,
                "broker_account_id": payload.broker_account_id,
                "inline_executions_count": len(payload.executions or []),
            },
        )
        await db.commit()
        return BrokerImportResponse(
            mode="async",
            import_run_id=import_run.id,
            status="queued",
            job_id=task_id,
        )

    import_run = ImportRun(
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        source=source,
        broker_account_id=payload.broker_account_id,
        window_start=payload.start_time,
        window_end=payload.end_time,
    )
    db.add(import_run)
    await db.flush()

    updated_run, summary = await run_import_sync(
        db,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        account_ref=payload.account_ref,
        broker_account_id=payload.broker_account_id,
        source=source,
        inline_executions=payload.executions,
        import_run=import_run,
    )
    return BrokerImportResponse(
        mode="sync",
        import_run_id=updated_run.id,
        status=updated_run.status,
        summary=ImportSummaryResponse(
            total_received=summary.total_received,
            imported=summary.imported,
            duplicates_skipped=summary.duplicates_skipped,
            failed=summary.failed,
            trades_created=summary.trades_created,
            trades_updated=summary.trades_updated,
            errors=list(summary.errors),
        ),
    )


def _enqueue_import_job(**kwargs: object) -> str:
    try:
        from app.worker.tasks import import_ibkr_executions
    except ModuleNotFoundError as exc:
        raise DomainValidationError(
            "Celery is not installed; set async_mode=false for synchronous imports"
        ) from exc
    task = import_ibkr_executions.delay(**kwargs)
    return str(task.id)
