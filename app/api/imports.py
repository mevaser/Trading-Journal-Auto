from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.import_schemas import ImportRunRead, ImportRunResponse
from app.auth.dependencies import (
    TenantRequestContext,
    get_request_tenant_context,
    require_tenant_context,
)
from app.db.session import get_db
from app.services.import_orchestrator import get_import_run_or_404, list_import_runs


router = APIRouter(
    prefix="/imports",
    tags=["Import Runs"],
    dependencies=[Depends(require_tenant_context)],
)


@router.get("/", response_model=list[ImportRunResponse])
async def get_import_runs(
    limit: int = Query(default=50, ge=1, le=200),
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[ImportRunResponse]:
    runs = await list_import_runs(db, tenant_id=tenant_ctx.tenant_id, limit=limit)
    return [ImportRunResponse.from_model(ImportRunRead.model_validate(item)) for item in runs]


@router.get("/{run_id}", response_model=ImportRunResponse)
async def get_import_run(
    run_id: int,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> ImportRunResponse:
    run = await get_import_run_or_404(db, run_id=run_id, tenant_id=tenant_ctx.tenant_id)
    return ImportRunResponse.from_model(ImportRunRead.model_validate(run))
