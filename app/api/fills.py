from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.fill_error_mapping import map_fill_integrity_error
from app.auth.dependencies import (
    TenantRequestContext,
    get_request_tenant_context,
    require_tenant_context,
)
from app.db.schemas import FillRead, FillUpdate
from app.db.session import get_db
from app.observability import DomainValidationError
from app.services.trade_service import get_fill_or_404, get_trade_or_404, recalculate_trade


router = APIRouter(prefix="/fills", tags=["Fills"], dependencies=[Depends(require_tenant_context)])


@router.patch("/{fill_id}", response_model=FillRead)
async def update_fill(
    fill_id: int,
    payload: FillUpdate,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    fill = await get_fill_or_404(db, fill_id, tenant_id=tenant_ctx.tenant_id)

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if field_name == "side" and value is not None:
            setattr(fill, field_name, value.upper())
        else:
            setattr(fill, field_name, value)

    trade = await get_trade_or_404(db, fill.trade_id, tenant_id=tenant_ctx.tenant_id)

    try:
        await db.flush()
        await recalculate_trade(db, trade)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise map_fill_integrity_error(exc, trade_id=trade.id, fill_id=fill_id) from exc
    except ValueError as exc:
        await db.rollback()
        raise DomainValidationError(str(exc), details={"fill_id": fill_id}) from exc

    await db.refresh(fill)
    return fill


@router.delete("/{fill_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_fill(
    fill_id: int,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    fill = await get_fill_or_404(db, fill_id, tenant_id=tenant_ctx.tenant_id)
    trade = await get_trade_or_404(db, fill.trade_id, tenant_id=tenant_ctx.tenant_id)

    await db.delete(fill)

    try:
        await db.flush()
        await recalculate_trade(db, trade)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise DomainValidationError(str(exc), details={"fill_id": fill_id}) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
