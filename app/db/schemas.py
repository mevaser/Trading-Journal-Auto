from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from typing import Optional

class TradeCreate(BaseModel):
    symbol: str
    entry_date: datetime
    entry_price: Decimal
    quantity: Decimal
    direction: str
    strategy: Optional[str] = None
    user_id: int  # 🔥 this is required!


class TradeRead(TradeCreate):
    id: int
    exit_date: Optional[datetime] = None
    exit_price: Optional[Decimal] = None
    pnl_usd: Optional[Decimal] = None
    pnl_pct: Optional[Decimal] = None
    is_intraday: Optional[bool] = None

    class Config:
        orm_mode = True

class TradeUpdate(BaseModel):
    exit_date: Optional[datetime] = None
    exit_price: Optional[Decimal] = None
    strategy: Optional[str] = None  # allow strategy change too

