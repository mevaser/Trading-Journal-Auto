from __future__ import annotations
import datetime
from decimal import Decimal
from typing import List
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
)


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class User(Base):
    """Represents a user in the system."""

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

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}')>"


class Trade(Base):
    """Represents a trade made by a user."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    symbol: Mapped[str] = mapped_column(String(20))
    entry_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    exit_date: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    quantity: Mapped[int] = mapped_column(Numeric(18, 8))
    direction: Mapped[str] = mapped_column(String(5))  # e.g., "LONG", "SHORT"
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pnl_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    is_intraday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user: Mapped["User"] = relationship(back_populates="trades")

    __table_args__ = (Index("ix_trades_symbol_entry_date", "symbol", "entry_date"),)

    def __repr__(self) -> str:
        return f"<Trade(id={self.id}, symbol='{self.symbol}', user_id={self.user_id})>"


class MarketData(Base):
    """Represents market data for a symbol on a specific date."""

    __tablename__ = "market_data"

    date: Mapped[datetime.date] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    close_price: Mapped[Decimal] = mapped_column(Numeric(10, 4))

    def __repr__(self) -> str:
        return f"<MarketData(date='{self.date}', symbol='{self.symbol}')>"
