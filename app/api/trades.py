from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.fill_error_mapping import map_fill_integrity_error
from app.auth.dependencies import (
    TenantRequestContext,
    get_request_tenant_context,
    require_tenant_context,
)
from app.db.models import Trade, TradeFill
from app.db.schemas import FillCreate, FillRead, TradeCreate, TradeRead, TradeUpdate
from app.db.session import get_db
from app.observability import DomainValidationError
from app.services.trade_service import (
    get_trade_or_404,
    list_trade_fills,
    list_trades,
    recalculate_trade,
)


router = APIRouter(prefix="/trades", tags=["Trades"], dependencies=[Depends(require_tenant_context)])


@router.get("/", response_model=list[TradeRead])
async def get_trades(
    symbol: Optional[str] = Query(default=None),
    strategy: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    direction: Optional[str] = Query(default=None),
    is_intraday: Optional[bool] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[Trade]:
    trades = await list_trades(
        db=db,
        tenant_id=tenant_ctx.tenant_id,
        symbol=symbol,
        strategy=strategy,
        status=status_filter,
        direction=direction,
        is_intraday=is_intraday,
    )

    if date_from is not None:
        trades = [item for item in trades if item.opened_at and item.opened_at >= date_from]
    if date_to is not None:
        trades = [item for item in trades if item.opened_at and item.opened_at <= date_to]

    return trades


@router.get("/{trade_id}", response_model=TradeRead)
async def get_trade(
    trade_id: int,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> Trade:
    return await get_trade_or_404(db, trade_id, tenant_id=tenant_ctx.tenant_id)


@router.post("/", response_model=TradeRead, status_code=status.HTTP_201_CREATED)
async def create_trade(
    payload: TradeCreate,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> Trade:
    trade = Trade(**payload.model_dump())
    trade.tenant_id = tenant_ctx.tenant_id
    trade.user_id = tenant_ctx.user_id
    trade.direction = trade.direction.upper()

    db.add(trade)
    await db.commit()
    return await get_trade_or_404(db, trade.id, tenant_id=tenant_ctx.tenant_id)


@router.patch("/{trade_id}", response_model=TradeRead)
async def update_trade(
    trade_id: int,
    payload: TradeUpdate,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> Trade:
    trade = await get_trade_or_404(db, trade_id, tenant_id=tenant_ctx.tenant_id)

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if field_name == "direction" and value is not None:
            setattr(trade, field_name, value.upper())
        else:
            setattr(trade, field_name, value)

    await db.commit()
    return await get_trade_or_404(db, trade_id, tenant_id=tenant_ctx.tenant_id)


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_trade(
    trade_id: int,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    trade = await get_trade_or_404(db, trade_id, tenant_id=tenant_ctx.tenant_id)
    await db.delete(trade)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{trade_id}/fills", response_model=list[FillRead])
async def get_trade_fills(
    trade_id: int,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[TradeFill]:
    await get_trade_or_404(db, trade_id, tenant_id=tenant_ctx.tenant_id)
    return await list_trade_fills(db, trade_id, tenant_id=tenant_ctx.tenant_id)


@router.post("/{trade_id}/fills", response_model=FillRead, status_code=status.HTTP_201_CREATED)
async def create_trade_fill(
    trade_id: int,
    payload: FillCreate,
    tenant_ctx: TenantRequestContext = Depends(get_request_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> TradeFill:
    trade = await get_trade_or_404(db, trade_id, tenant_id=tenant_ctx.tenant_id)

    fill = TradeFill(trade_id=trade.id, tenant_id=trade.tenant_id, **payload.model_dump())
    fill.side = fill.side.upper()
    db.add(fill)

    try:
        await db.flush()
        await recalculate_trade(db, trade)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise map_fill_integrity_error(exc, trade_id=trade_id) from exc
    except ValueError as exc:
        await db.rollback()
        raise DomainValidationError(str(exc), details={"trade_id": trade_id}) from exc

    await db.refresh(fill)
    return fill
