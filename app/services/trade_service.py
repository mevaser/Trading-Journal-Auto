from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Trade, TradeFill
from app.services.calculation_service import calculate_trade_metrics


async def get_trade_or_404(db: AsyncSession, trade_id: int) -> Trade:
    stmt = select(Trade).options(selectinload(Trade.fills)).where(Trade.id == trade_id)
    trade = (await db.execute(stmt)).scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return trade


async def get_fill_or_404(db: AsyncSession, fill_id: int) -> TradeFill:
    fill = await db.get(TradeFill, fill_id)
    if fill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fill not found")
    return fill


async def list_trade_fills(db: AsyncSession, trade_id: int) -> list[TradeFill]:
    stmt = (
        select(TradeFill)
        .where(TradeFill.trade_id == trade_id)
        .order_by(TradeFill.fill_datetime.asc(), TradeFill.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def recalculate_trade(db: AsyncSession, trade: Trade) -> None:
    fills = await list_trade_fills(db, trade.id)
    metrics = calculate_trade_metrics(trade, fills)

    trade.opened_at = metrics.opened_at
    trade.closed_at = metrics.closed_at
    trade.avg_entry_price = metrics.avg_entry_price
    trade.avg_exit_price = metrics.avg_exit_price
    trade.quantity_opened = metrics.quantity_opened
    trade.quantity_closed = metrics.quantity_closed
    trade.remaining_quantity = metrics.remaining_quantity
    trade.pnl_usd = metrics.pnl_usd
    trade.pnl_pct = metrics.pnl_pct
    trade.status = metrics.status
    trade.is_intraday = metrics.is_intraday
    trade.duration_days = metrics.duration_days

    # Keep legacy denormalized fields aligned with fill-based metrics.
    trade.entry_date = metrics.opened_at
    trade.exit_date = metrics.closed_at
    trade.entry_price = metrics.avg_entry_price
    trade.exit_price = metrics.avg_exit_price
    trade.quantity = metrics.quantity_opened


async def list_trades(
    db: AsyncSession,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    status: Optional[str] = None,
    direction: Optional[str] = None,
    is_intraday: Optional[bool] = None,
) -> list[Trade]:
    stmt = select(Trade).options(selectinload(Trade.fills))

    if symbol:
        stmt = stmt.where(Trade.symbol == symbol)
    if strategy:
        stmt = stmt.where(Trade.strategy == strategy)
    if status:
        stmt = stmt.where(Trade.status == status)
    if direction:
        stmt = stmt.where(Trade.direction == direction.upper())
    if is_intraday is not None:
        stmt = stmt.where(Trade.is_intraday == is_intraday)

    result = await db.execute(stmt.order_by(Trade.created_at.desc(), Trade.id.desc()))
    return list(result.scalars().all())
