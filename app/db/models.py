from __future__ import annotations

import datetime
from decimal import Decimal
from typing import List

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.types import UTCDateTime


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for SQLAlchemy models."""


class Tenant(Base):
    """Platform-managed tenant identity and ownership root."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[List["Membership"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    trades: Mapped[List["Trade"]] = relationship(back_populates="tenant")
    fills: Mapped[List["TradeFill"]] = relationship(back_populates="tenant", overlaps="trade,fills")


class User(Base):
    """Platform-managed user identity."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[List["Membership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    trades: Mapped[List["Trade"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Membership(Base):
    """User-to-tenant authorization link."""

    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member", server_default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        Index("ix_memberships_user_tenant", "user_id", "tenant_id"),
    )


class Trade(Base):
    """Represents a position/trade idea that may contain multiple fills."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), index=True, default=1, server_default=text("1")
    )
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

    tenant: Mapped["Tenant"] = relationship(back_populates="trades")
    user: Mapped["User"] = relationship(back_populates="trades")
    fills: Mapped[List["TradeFill"]] = relationship(
        back_populates="trade",
        cascade="all, delete-orphan",
        order_by="TradeFill.fill_datetime",
        overlaps="tenant,fills",
    )

    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_trades_id_tenant"),
        CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_trades_direction_valid"),
        CheckConstraint("status IN ('open', 'partial', 'closed')", name="ck_trades_status_valid"),
        CheckConstraint(
            "opened_at IS NULL OR closed_at IS NULL OR closed_at >= opened_at",
            name="ck_trades_closed_at_after_opened_at",
        ),
        CheckConstraint("quantity_opened IS NULL OR quantity_opened >= 0", name="ck_trades_quantity_opened_non_negative"),
        CheckConstraint("quantity_closed IS NULL OR quantity_closed >= 0", name="ck_trades_quantity_closed_non_negative"),
        CheckConstraint(
            "remaining_quantity IS NULL OR remaining_quantity >= 0",
            name="ck_trades_remaining_quantity_non_negative",
        ),
        CheckConstraint("duration_days IS NULL OR duration_days >= 0", name="ck_trades_duration_days_non_negative"),
        Index("ix_trades_tenant_symbol_entry_date", "tenant_id", "symbol", "entry_date"),
        Index("ix_trades_tenant_status", "tenant_id", "status"),
        Index("ix_trades_tenant_created_at_id", "tenant_id", "created_at", "id"),
        Index("ix_trades_tenant_opened_at", "tenant_id", "opened_at"),
        Index("ix_trades_tenant_strategy_opened_at", "tenant_id", "strategy", "opened_at"),
    )


class TradeFill(Base):
    """Represents a single execution/fill connected to a trade."""

    __tablename__ = "trade_fills"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    trade_id: Mapped[int] = mapped_column(index=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), index=True, default=1, server_default=text("1")
    )
    fill_datetime: Mapped[datetime.datetime] = mapped_column(UTCDateTime())
    side: Mapped[str] = mapped_column(String(4))  # BUY or SELL
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    commission: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True, default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(20), default="manual")
    external_fill_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="fills", overlaps="trade,fills")
    trade: Mapped["Trade"] = relationship(back_populates="fills", overlaps="tenant,fills")

    __table_args__ = (
        ForeignKeyConstraint(
            ["trade_id", "tenant_id"],
            ["trades.id", "trades.tenant_id"],
            ondelete="CASCADE",
            name="fk_trade_fills_trade_tenant",
        ),
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_trade_fills_side_valid"),
        CheckConstraint("quantity > 0", name="ck_trade_fills_quantity_positive"),
        CheckConstraint("price > 0", name="ck_trade_fills_price_positive"),
        CheckConstraint("commission IS NULL OR commission >= 0", name="ck_trade_fills_commission_non_negative"),
        CheckConstraint("length(trim(source)) > 0", name="ck_trade_fills_source_non_empty"),
        CheckConstraint(
            "external_fill_id IS NULL OR length(trim(external_fill_id)) > 0",
            name="ck_trade_fills_external_fill_id_non_empty",
        ),
        UniqueConstraint("tenant_id", "external_fill_id", name="uq_trade_fills_tenant_external_fill_id"),
        Index("ix_trade_fills_tenant_trade_fill_datetime", "tenant_id", "trade_id", "fill_datetime"),
        Index("ix_trade_fills_trade_fill_datetime", "trade_id", "fill_datetime"),
        Index("ix_trade_fills_tenant_fill_datetime", "tenant_id", "fill_datetime"),
    )


class MarketData(Base):
    """Represents benchmark/market closes for a specific date."""

    __tablename__ = "market_data"

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    close_price: Mapped[Decimal] = mapped_column(Numeric(10, 4))
