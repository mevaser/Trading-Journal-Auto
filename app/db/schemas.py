from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.datetime_utils import normalize_datetime_to_utc


DirectionType = Literal["LONG", "SHORT"]
SideType = Literal["BUY", "SELL"]
StatusType = Literal["open", "partial", "closed"]


class FillBase(BaseModel):
    fill_datetime: datetime
    side: SideType
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    source: str = "manual"
    external_fill_id: Optional[str] = None

    @field_validator("fill_datetime")
    @classmethod
    def normalize_fill_datetime(cls, value: datetime) -> datetime:
        return normalize_datetime_to_utc(value)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("quantity")
    @classmethod
    def validate_quantity_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("quantity must be greater than 0")
        return value

    @field_validator("price")
    @classmethod
    def validate_price_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("price must be greater than 0")
        return value

    @field_validator("commission")
    @classmethod
    def validate_commission_non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("commission must be greater than or equal to 0")
        return value


class FillCreate(FillBase):
    pass


class FillUpdate(BaseModel):
    fill_datetime: Optional[datetime] = None
    side: Optional[SideType] = None
    quantity: Optional[Decimal] = Field(default=None, gt=0)
    price: Optional[Decimal] = Field(default=None, gt=0)
    commission: Optional[Decimal] = Field(default=None, ge=0)
    source: Optional[str] = None
    external_fill_id: Optional[str] = None

    @field_validator("fill_datetime")
    @classmethod
    def normalize_fill_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return normalize_datetime_to_utc(value)

    @field_validator("quantity")
    @classmethod
    def validate_quantity_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("quantity must be greater than 0")
        return value

    @field_validator("price")
    @classmethod
    def validate_price_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("price must be greater than 0")
        return value

    @field_validator("commission")
    @classmethod
    def validate_commission_non_negative(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value < 0:
            raise ValueError("commission must be greater than or equal to 0")
        return value


class FillRead(FillBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trade_id: int
    created_at: datetime


class TradeBase(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    direction: DirectionType
    asset_type: Optional[str] = None
    strategy: Optional[str] = None
    thesis: Optional[str] = None
    reason_entry: Optional[str] = None
    reason_exit: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None


class TradeCreate(TradeBase):
    user_id: int = 1


class TradeUpdate(BaseModel):
    symbol: Optional[str] = Field(default=None, min_length=1, max_length=20)
    direction: Optional[DirectionType] = None
    asset_type: Optional[str] = None
    strategy: Optional[str] = None
    thesis: Optional[str] = None
    reason_entry: Optional[str] = None
    reason_exit: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None


class TradeRead(TradeBase):
    """Canonical trade response: metadata + fills + derived fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: StatusType

    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    avg_entry_price: Optional[Decimal] = None
    avg_exit_price: Optional[Decimal] = None
    quantity_opened: Optional[Decimal] = None
    quantity_closed: Optional[Decimal] = None
    remaining_quantity: Optional[Decimal] = None
    pnl_usd: Optional[Decimal] = None
    pnl_pct: Optional[Decimal] = None
    is_intraday: Optional[bool] = None
    duration_days: Optional[int] = None

    created_at: datetime
    updated_at: datetime

    fills: list[FillRead] = Field(default_factory=list)
