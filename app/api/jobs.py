from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.import_schemas import JobRunResponse
from app.auth.dependencies import (
    TenantRequestContext,
    get_request_tenant_context,
    require_tenant_context,
)
from app.db.session import get_db
from app.services.import_orchestrator import get_job_run_or_404


router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
    dependencies=[Depends(require_tenant_context)],
)


@router.get("/{job_id}", response_model=JobRunResponse)
async def get_job_status(
    job_id: str,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> JobRunResponse:
    job = await get_job_run_or_404(db, external_job_id=job_id, tenant_id=tenant_ctx.tenant_id)
    return JobRunResponse.model_validate(job, from_attributes=True)
