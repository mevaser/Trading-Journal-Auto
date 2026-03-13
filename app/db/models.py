from __future__ import annotations

import datetime
from decimal import Decimal
from typing import List

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.types import UTCDateTime


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for SQLAlchemy models."""


class User(Base):
    """Single-user placeholder model for future auth support."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trades: Mapped[List["Trade"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Trade(Base):
    """Represents a position/trade idea that may contain multiple fills."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)

    symbol: Mapped[str] = mapped_column(String(20), index=True)
    asset_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)
    direction: Mapped[str] = mapped_column(String(5))  # LONG or SHORT
    thesis: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reason_entry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason_exit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open")

    # Legacy fields kept for compatibility and populated by service calculations.
    entry_date: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    exit_date: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    portfolio_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    estimates: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    # Derived metrics (server-side managed)
    opened_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avg_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    avg_exit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    quantity_opened: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    quantity_closed: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    remaining_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    pnl_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    is_intraday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="trades")
    fills: Mapped[List["TradeFill"]] = relationship(
        back_populates="trade", cascade="all, delete-orphan", order_by="TradeFill.fill_datetime"
    )

    __table_args__ = (
        Index("ix_trades_symbol_entry_date", "symbol", "entry_date"),
        Index("ix_trades_status", "status"),
    )


class TradeFill(Base):
    """Represents a single execution/fill connected to a trade."""

    __tablename__ = "trade_fills"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), index=True)
    fill_datetime: Mapped[datetime.datetime] = mapped_column(UTCDateTime())
    side: Mapped[str] = mapped_column(String(4))  # BUY or SELL
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    commission: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True, default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(20), default="manual")
    external_fill_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trade: Mapped["Trade"] = relationship(back_populates="fills")

    __table_args__ = (Index("ix_trade_fills_trade_id_fill_datetime", "trade_id", "fill_datetime"),)


class MarketData(Base):
    """Represents benchmark/market closes for a specific date."""

    __tablename__ = "market_data"

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    close_price: Mapped[Decimal] = mapped_column(Numeric(10, 4))
