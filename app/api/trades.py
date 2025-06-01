from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.session import get_db
from app.db import models
from app.db.schemas import TradeCreate, TradeRead, TradeUpdate
from app.utils.trade_metrics import calculate_trade_metrics
from fastapi import HTTPException
from sqlalchemy import update
from typing import Optional


router = APIRouter(prefix="/trades", tags=["Trades"])

from fastapi import Query
from datetime import datetime

@router.get("/", response_model=list[TradeRead])
async def list_trades(
    symbol: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    query = select(models.Trade)

    if symbol:
        query = query.where(models.Trade.symbol == symbol)
    if direction:
        query = query.where(models.Trade.direction == direction)
    if from_date:
        query = query.where(models.Trade.entry_date >= from_date)
    if to_date:
        query = query.where(models.Trade.entry_date <= to_date)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=TradeRead)
async def create_trade(trade: TradeCreate, db: AsyncSession = Depends(get_db)):
    new_trade = models.Trade(**trade.dict())
    db.add(new_trade)
    await db.commit()
    await db.refresh(new_trade)

    # calculate trade metrics
    calculate_trade_metrics(new_trade)

    #update the trade with computed fields
    await db.commit()
    await db.refresh(new_trade)
    return new_trade

@router.put("/{trade_id}", response_model=TradeRead)
async def update_trade(trade_id: int, trade_update: TradeUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Trade).where(models.Trade.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Update fields that were provided
    for field, value in trade_update.dict(exclude_unset=True).items():
        setattr(trade, field, value)

    # Recalculate trade metrics if exit info is provided
    calculate_trade_metrics(trade)

    await db.commit()
    await db.refresh(trade)
    return trade