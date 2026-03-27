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
    Text,
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
    import_runs: Mapped[List["ImportRun"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    import_run_records: Mapped[List["ImportRunRecord"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    broker_execution_fills: Mapped[List["BrokerExecutionFill"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    trade_lifecycles: Mapped[List["TradeLifecycleProjection"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    trade_lifecycle_execution_allocations: Mapped[List["TradeLifecycleExecutionAllocation"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    trade_lifecycle_projection_states: Mapped[List["TradeLifecycleProjectionState"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    job_runs: Mapped[List["JobRun"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


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
    import_runs: Mapped[List["ImportRun"]] = relationship(back_populates="user")
    job_runs: Mapped[List["JobRun"]] = relationship(back_populates="user")


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
    canonical_execution_fill_id: Mapped[int | None] = mapped_column(
        ForeignKey("broker_execution_fills.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="fills", overlaps="trade,fills")
    trade: Mapped["Trade"] = relationship(back_populates="fills", overlaps="tenant,fills")
    canonical_execution_fill: Mapped["BrokerExecutionFill | None"] = relationship()

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
        UniqueConstraint(
            "tenant_id",
            "source",
            "external_fill_id",
            name="uq_trade_fills_tenant_source_external_fill_id",
        ),
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


class ImportRun(Base):
    """Audit record for a single import execution request."""

    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="ibkr", server_default="ibkr")
    broker_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    window_start: Mapped[datetime.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    window_end: Mapped[datetime.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    total_received: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    imported: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    failed: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    trades_created: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    trades_updated: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="import_runs")
    user: Mapped["User"] = relationship(back_populates="import_runs")
    records: Mapped[List["ImportRunRecord"]] = relationship(
        back_populates="import_run", cascade="all, delete-orphan"
    )
    canonical_execution_fills: Mapped[List["BrokerExecutionFill"]] = relationship(
        back_populates="import_run"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_import_runs_status_valid",
        ),
        CheckConstraint("total_received >= 0", name="ck_import_runs_total_received_non_negative"),
        CheckConstraint("imported >= 0", name="ck_import_runs_imported_non_negative"),
        CheckConstraint("duplicates_skipped >= 0", name="ck_import_runs_duplicates_skipped_non_negative"),
        CheckConstraint("failed >= 0", name="ck_import_runs_failed_non_negative"),
        CheckConstraint("trades_created >= 0", name="ck_import_runs_trades_created_non_negative"),
        CheckConstraint("trades_updated >= 0", name="ck_import_runs_trades_updated_non_negative"),
        CheckConstraint("error_count >= 0", name="ck_import_runs_error_count_non_negative"),
        Index("ix_import_runs_tenant_created_at", "tenant_id", "created_at"),
    )


class JobRun(Base):
    """Background job execution tracking."""

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    import_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(String(32), default="ibkr_import", server_default="ibkr_import")
    provider: Mapped[str] = mapped_column(String(16), default="celery", server_default="celery")
    external_job_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="job_runs")
    user: Mapped["User"] = relationship(back_populates="job_runs")
    import_run: Mapped[ImportRun | None] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_job_runs_status_valid",
        ),
        Index("ix_job_runs_tenant_status_created_at", "tenant_id", "status", "created_at"),
    )


class BrokerExecutionFill(Base):
    """Immutable canonical broker execution row."""

    __tablename__ = "broker_execution_fills"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    import_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    source: Mapped[str] = mapped_column(String(32), nullable=False, default="ibkr", server_default="ibkr")
    broker_account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    external_execution_id: Mapped[str] = mapped_column(String(120), nullable=False)

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    commission: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    execution_time_utc: Mapped[datetime.datetime] = mapped_column(UTCDateTime(), nullable=False)

    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    supersedes_execution_fill_id: Mapped[int | None] = mapped_column(
        ForeignKey("broker_execution_fills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    superseded_by_execution_fill_id: Mapped[int | None] = mapped_column(
        ForeignKey("broker_execution_fills.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="broker_execution_fills")
    import_run: Mapped["ImportRun | None"] = relationship(back_populates="canonical_execution_fills")
    lifecycle_allocations: Mapped[List["TradeLifecycleExecutionAllocation"]] = relationship(
        back_populates="canonical_execution_fill"
    )
    supersedes_execution_fill: Mapped["BrokerExecutionFill | None"] = relationship(
        foreign_keys=[supersedes_execution_fill_id], remote_side=[id]
    )
    superseded_by_execution_fill: Mapped["BrokerExecutionFill | None"] = relationship(
        foreign_keys=[superseded_by_execution_fill_id], remote_side=[id], post_update=True
    )

    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_broker_execution_fills_side_valid"),
        CheckConstraint("quantity > 0", name="ck_broker_execution_fills_quantity_positive"),
        CheckConstraint("price > 0", name="ck_broker_execution_fills_price_positive"),
        CheckConstraint("commission >= 0", name="ck_broker_execution_fills_commission_non_negative"),
        CheckConstraint("length(trim(source)) > 0", name="ck_broker_execution_fills_source_non_empty"),
        CheckConstraint(
            "length(trim(broker_account_id)) > 0", name="ck_broker_execution_fills_broker_account_non_empty"
        ),
        CheckConstraint(
            "length(trim(external_execution_id)) > 0",
            name="ck_broker_execution_fills_external_execution_non_empty",
        ),
        UniqueConstraint(
            "tenant_id",
            "source",
            "broker_account_id",
            "external_execution_id",
            "is_active",
            name="uq_broker_execution_fills_identity_active",
        ),
        Index(
            "ix_broker_execution_fills_identity_lookup",
            "tenant_id",
            "source",
            "broker_account_id",
            "external_execution_id",
            "is_active",
        ),
        Index("ix_broker_execution_fills_tenant_symbol_time", "tenant_id", "symbol", "execution_time_utc", "id"),
    )


class ImportRunRecord(Base):
    """Per-record staging and terminal processing outcome for one import run."""

    __tablename__ = "import_run_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    record_seq: Mapped[int] = mapped_column(Integer, nullable=False)

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    broker_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_execution_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    side: Mapped[str | None] = mapped_column(String(4), nullable=True)
    asset_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    commission: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    execution_time_utc: Mapped[datetime.datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staged", server_default="staged")
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_execution_fill_id: Mapped[int | None] = mapped_column(
        ForeignKey("broker_execution_fills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    import_run: Mapped["ImportRun"] = relationship(back_populates="records")
    tenant: Mapped["Tenant"] = relationship(back_populates="import_run_records")
    canonical_execution_fill: Mapped["BrokerExecutionFill | None"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('staged', 'duplicate_skipped', 'resolved_inserted', 'resolved_superseded', 'failed_validation', 'failed_processing')",
            name="ck_import_run_records_status_valid",
        ),
        CheckConstraint("record_seq > 0", name="ck_import_run_records_record_seq_positive"),
        UniqueConstraint("import_run_id", "record_seq", name="uq_import_run_records_import_run_record_seq"),
        Index("ix_import_run_records_tenant_run_status", "tenant_id", "import_run_id", "status"),
        Index(
            "ix_import_run_records_identity_lookup",
            "tenant_id",
            "source",
            "broker_account_id",
            "external_execution_id",
        ),
    )


class TradeLifecycleProjectionState(Base):
    """Tracks projection generation and dirty rebuild state per canonical partition."""

    __tablename__ = "trade_lifecycle_projection_state"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    broker_account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    projection_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    current_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    is_dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    earliest_dirty_execution_time_utc: Mapped[datetime.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_rebuilt_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rebuild_from_execution_time_utc: Mapped[datetime.datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    last_canonical_execution_time_utc: Mapped[datetime.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_canonical_execution_fill_id: Mapped[int | None] = mapped_column(
        ForeignKey("broker_execution_fills.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="trade_lifecycle_projection_states")
    last_canonical_execution_fill: Mapped["BrokerExecutionFill | None"] = relationship()
    lifecycles: Mapped[List["TradeLifecycleProjection"]] = relationship(
        back_populates="projection_state", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("projection_version > 0", name="ck_trade_lifecycle_projection_state_projection_version_positive"),
        CheckConstraint("current_generation >= 0", name="ck_trade_lifecycle_projection_state_generation_non_negative"),
        CheckConstraint("length(trim(source)) > 0", name="ck_trade_lifecycle_projection_state_source_non_empty"),
        CheckConstraint(
            "length(trim(broker_account_id)) > 0",
            name="ck_trade_lifecycle_projection_state_broker_account_non_empty",
        ),
        CheckConstraint("length(trim(symbol)) > 0", name="ck_trade_lifecycle_projection_state_symbol_non_empty"),
        CheckConstraint("length(trim(asset_type)) > 0", name="ck_trade_lifecycle_projection_state_asset_type_non_empty"),
        UniqueConstraint(
            "tenant_id",
            "source",
            "broker_account_id",
            "symbol",
            "asset_type",
            name="uq_trade_lifecycle_projection_state_partition",
        ),
        Index("ix_trade_lifecycle_projection_state_tenant_dirty", "tenant_id", "is_dirty"),
    )


class TradeLifecycleProjection(Base):
    """Current persisted lifecycle projection row for one partition/generation."""

    __tablename__ = "trade_lifecycles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    projection_state_id: Mapped[int] = mapped_column(
        ForeignKey("trade_lifecycle_projection_state.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    broker_account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    projection_version: Mapped[int] = mapped_column(Integer, nullable=False)
    projection_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(5), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    opened_at: Mapped[datetime.datetime] = mapped_column(UTCDateTime(), nullable=False)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    entry_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    exit_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    avg_exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="trade_lifecycles")
    projection_state: Mapped["TradeLifecycleProjectionState"] = relationship(back_populates="lifecycles")
    allocations: Mapped[List["TradeLifecycleExecutionAllocation"]] = relationship(
        back_populates="trade_lifecycle",
        cascade="all, delete-orphan",
        order_by="TradeLifecycleExecutionAllocation.allocation_seq",
    )

    __table_args__ = (
        CheckConstraint("projection_version > 0", name="ck_trade_lifecycles_projection_version_positive"),
        CheckConstraint("projection_generation >= 0", name="ck_trade_lifecycles_generation_non_negative"),
        CheckConstraint("lifecycle_seq > 0", name="ck_trade_lifecycles_lifecycle_seq_positive"),
        CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_trade_lifecycles_direction_valid"),
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_trade_lifecycles_status_valid"),
        CheckConstraint("entry_quantity >= 0", name="ck_trade_lifecycles_entry_quantity_non_negative"),
        CheckConstraint("exit_quantity >= 0", name="ck_trade_lifecycles_exit_quantity_non_negative"),
        CheckConstraint("remaining_quantity >= 0", name="ck_trade_lifecycles_remaining_quantity_non_negative"),
        CheckConstraint(
            "closed_at IS NULL OR closed_at >= opened_at",
            name="ck_trade_lifecycles_closed_at_after_opened_at",
        ),
        CheckConstraint(
            "remaining_quantity = entry_quantity - exit_quantity",
            name="ck_trade_lifecycles_remaining_quantity_consistent",
        ),
        UniqueConstraint(
            "projection_state_id",
            "projection_generation",
            "lifecycle_seq",
            name="uq_trade_lifecycles_state_generation_seq",
        ),
        Index("ix_trade_lifecycles_partition_opened_at", "tenant_id", "source", "broker_account_id", "symbol", "opened_at"),
        Index(
            "ix_trade_lifecycles_partition_status_opened_at",
            "tenant_id",
            "source",
            "broker_account_id",
            "symbol",
            "status",
            "opened_at",
        ),
    )


class TradeLifecycleExecutionAllocation(Base):
    """Maps canonical execution slices into persisted lifecycle rows."""

    __tablename__ = "trade_lifecycle_execution_allocations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    trade_lifecycle_id: Mapped[int] = mapped_column(
        ForeignKey("trade_lifecycles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    canonical_execution_fill_id: Mapped[int] = mapped_column(
        ForeignKey("broker_execution_fills.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    projection_version: Mapped[int] = mapped_column(Integer, nullable=False)
    projection_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    allocation_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    allocation_role: Mapped[str] = mapped_column(String(5), nullable=False)
    allocated_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    execution_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    execution_time_utc: Mapped[datetime.datetime] = mapped_column(UTCDateTime(), nullable=False)
    is_flip_slice: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="trade_lifecycle_execution_allocations")
    trade_lifecycle: Mapped["TradeLifecycleProjection"] = relationship(back_populates="allocations")
    canonical_execution_fill: Mapped["BrokerExecutionFill"] = relationship(back_populates="lifecycle_allocations")

    __table_args__ = (
        CheckConstraint("projection_version > 0", name="ck_trade_lifecycle_execution_allocations_projection_version_positive"),
        CheckConstraint(
            "projection_generation >= 0",
            name="ck_trade_lifecycle_execution_allocations_generation_non_negative",
        ),
        CheckConstraint("allocation_seq > 0", name="ck_trade_lifecycle_execution_allocations_seq_positive"),
        CheckConstraint(
            "allocation_role IN ('ENTRY', 'EXIT')",
            name="ck_trade_lifecycle_execution_allocations_role_valid",
        ),
        CheckConstraint(
            "allocated_quantity > 0",
            name="ck_trade_lifecycle_execution_allocations_quantity_positive",
        ),
        UniqueConstraint(
            "trade_lifecycle_id",
            "allocation_seq",
            name="uq_trade_lifecycle_execution_allocations_lifecycle_seq",
        ),
        Index(
            "ix_trade_lifecycle_execution_allocations_tenant_canonical",
            "tenant_id",
            "canonical_execution_fill_id",
        ),
        Index(
            "ix_trade_lifecycle_execution_allocations_tenant_execution_time",
            "tenant_id",
            "execution_time_utc",
        ),
    )
