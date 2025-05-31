from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.session import get_db
from app.db import models
from app.db.schemas import TradeCreate, TradeRead
from app.utils.trade_metrics import calculate_trade_metrics

router = APIRouter(prefix="/trades", tags=["Trades"])

@router.get("/", response_model=list[TradeRead])
async def list_trades(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Trade))
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
