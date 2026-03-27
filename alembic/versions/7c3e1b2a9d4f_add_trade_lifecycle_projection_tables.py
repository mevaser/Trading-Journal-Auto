"""Add trade lifecycle projection tables

Revision ID: 7c3e1b2a9d4f
Revises: 9a7d1c2b4e8f
Create Date: 2026-03-24 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c3e1b2a9d4f"
down_revision: Union[str, None] = "9a7d1c2b4e8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trade_lifecycle_projection_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("broker_account_id", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("projection_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("current_generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_dirty", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("earliest_dirty_execution_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rebuilt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rebuild_from_execution_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_canonical_execution_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_canonical_execution_fill_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("projection_version > 0", name="ck_tlps_proj_ver_pos"),
        sa.CheckConstraint("current_generation >= 0", name="ck_tlps_gen_nonneg"),
        sa.CheckConstraint("length(trim(source)) > 0", name="ck_tlps_source_nonempty"),
        sa.CheckConstraint("length(trim(broker_account_id)) > 0", name="ck_tlps_acct_nonempty"),
        sa.CheckConstraint("length(trim(symbol)) > 0", name="ck_tlps_symbol_nonempty"),
        sa.CheckConstraint("length(trim(asset_type)) > 0", name="ck_tlps_asset_type_nonempty"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name="fk_tlps_tenant"),
        sa.ForeignKeyConstraint(
            ["last_canonical_execution_fill_id"],
            ["broker_execution_fills.id"],
            ondelete="SET NULL",
            name="fk_tlps_last_canon_fill",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source",
            "broker_account_id",
            "symbol",
            "asset_type",
            name="uq_tlps_partition",
        ),
    )
    op.create_index("ix_tlps_id", "trade_lifecycle_projection_state", ["id"], unique=False)
    op.create_index(
        "ix_tlps_tenant_dirty",
        "trade_lifecycle_projection_state",
        ["tenant_id", "is_dirty"],
        unique=False,
    )
    op.create_index(
        "ix_tlps_tenant_id",
        "trade_lifecycle_projection_state",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_tlps_last_canon_fill_id",
        "trade_lifecycle_projection_state",
        ["last_canonical_execution_fill_id"],
        unique=False,
    )

    op.create_table(
        "trade_lifecycles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("projection_state_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("broker_account_id", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("projection_version", sa.Integer(), nullable=False),
        sa.Column("projection_generation", sa.Integer(), nullable=False),
        sa.Column("lifecycle_seq", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_quantity", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("exit_quantity", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("remaining_quantity", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("avg_exit_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("projection_version > 0", name="ck_tl_proj_ver_pos"),
        sa.CheckConstraint("projection_generation >= 0", name="ck_tl_gen_nonneg"),
        sa.CheckConstraint("lifecycle_seq > 0", name="ck_tl_seq_pos"),
        sa.CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_tl_direction_valid"),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_tl_status_valid"),
        sa.CheckConstraint("entry_quantity >= 0", name="ck_tl_entry_qty_nonneg"),
        sa.CheckConstraint("exit_quantity >= 0", name="ck_tl_exit_qty_nonneg"),
        sa.CheckConstraint("remaining_quantity >= 0", name="ck_tl_rem_qty_nonneg"),
        sa.CheckConstraint("closed_at IS NULL OR closed_at >= opened_at", name="ck_tl_closed_after_open"),
        sa.CheckConstraint(
            "remaining_quantity = entry_quantity - exit_quantity",
            name="ck_tl_rem_qty_consistent",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name="fk_tl_tenant"),
        sa.ForeignKeyConstraint(
            ["projection_state_id"],
            ["trade_lifecycle_projection_state.id"],
            ondelete="CASCADE",
            name="fk_tl_proj_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_tl_id_tenant"),
        sa.UniqueConstraint(
            "projection_state_id",
            "projection_generation",
            "lifecycle_seq",
            name="uq_tl_state_gen_seq",
        ),
    )
    op.create_index("ix_tl_id", "trade_lifecycles", ["id"], unique=False)
    op.create_index("ix_tl_tenant_id", "trade_lifecycles", ["tenant_id"], unique=False)
    op.create_index("ix_tl_proj_state_id", "trade_lifecycles", ["projection_state_id"], unique=False)
    op.create_index("ix_tl_proj_gen", "trade_lifecycles", ["projection_generation"], unique=False)
    op.create_index(
        "ix_tl_part_opened_at",
        "trade_lifecycles",
        ["tenant_id", "source", "broker_account_id", "symbol", "asset_type", "opened_at"],
        unique=False,
    )
    op.create_index(
        "ix_tl_part_status_opened",
        "trade_lifecycles",
        ["tenant_id", "source", "broker_account_id", "symbol", "asset_type", "status", "opened_at"],
        unique=False,
    )

    op.create_table(
        "trade_lifecycle_execution_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("trade_lifecycle_id", sa.Integer(), nullable=False),
        sa.Column("canonical_execution_fill_id", sa.Integer(), nullable=False),
        sa.Column("projection_version", sa.Integer(), nullable=False),
        sa.Column("projection_generation", sa.Integer(), nullable=False),
        sa.Column("allocation_seq", sa.Integer(), nullable=False),
        sa.Column("allocation_role", sa.String(length=5), nullable=False),
        sa.Column("allocated_quantity", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("execution_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("execution_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_flip_slice", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("projection_version > 0", name="ck_tlea_proj_ver_pos"),
        sa.CheckConstraint("projection_generation >= 0", name="ck_tlea_gen_nonneg"),
        sa.CheckConstraint("allocation_seq > 0", name="ck_tlea_seq_pos"),
        sa.CheckConstraint("allocation_role IN ('ENTRY', 'EXIT')", name="ck_tlea_role_valid"),
        sa.CheckConstraint("allocated_quantity > 0", name="ck_tlea_qty_pos"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name="fk_tlea_tenant"),
        sa.ForeignKeyConstraint(
            ["trade_lifecycle_id", "tenant_id"],
            ["trade_lifecycles.id", "trade_lifecycles.tenant_id"],
            ondelete="CASCADE",
            name="fk_tlea_tl_id_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_execution_fill_id"],
            ["broker_execution_fills.id"],
            ondelete="RESTRICT",
            name="fk_tlea_canon_fill",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trade_lifecycle_id",
            "allocation_seq",
            name="uq_tlea_lifecycle_seq",
        ),
    )
    op.create_index(
        "ix_tlea_id",
        "trade_lifecycle_execution_allocations",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_tlea_tenant_id",
        "trade_lifecycle_execution_allocations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_tlea_trade_lifecycle_id",
        "trade_lifecycle_execution_allocations",
        ["trade_lifecycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_tlea_canon_fill_id",
        "trade_lifecycle_execution_allocations",
        ["canonical_execution_fill_id"],
        unique=False,
    )
    op.create_index(
        "ix_tlea_tenant_canon",
        "trade_lifecycle_execution_allocations",
        ["tenant_id", "canonical_execution_fill_id"],
        unique=False,
    )
    op.create_index(
        "ix_tlea_tenant_exec_time",
        "trade_lifecycle_execution_allocations",
        ["tenant_id", "execution_time_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tlea_tenant_exec_time", table_name="trade_lifecycle_execution_allocations")
    op.drop_index("ix_tlea_tenant_canon", table_name="trade_lifecycle_execution_allocations")
    op.drop_index("ix_tlea_canon_fill_id", table_name="trade_lifecycle_execution_allocations")
    op.drop_index("ix_tlea_trade_lifecycle_id", table_name="trade_lifecycle_execution_allocations")
    op.drop_index("ix_tlea_tenant_id", table_name="trade_lifecycle_execution_allocations")
    op.drop_index("ix_tlea_id", table_name="trade_lifecycle_execution_allocations")
    op.drop_table("trade_lifecycle_execution_allocations")

    op.drop_index("ix_tl_part_status_opened", table_name="trade_lifecycles")
    op.drop_index("ix_tl_part_opened_at", table_name="trade_lifecycles")
    op.drop_index("ix_tl_proj_gen", table_name="trade_lifecycles")
    op.drop_index("ix_tl_proj_state_id", table_name="trade_lifecycles")
    op.drop_index("ix_tl_tenant_id", table_name="trade_lifecycles")
    op.drop_index("ix_tl_id", table_name="trade_lifecycles")
    op.drop_table("trade_lifecycles")

    op.drop_index("ix_tlps_last_canon_fill_id", table_name="trade_lifecycle_projection_state")
    op.drop_index("ix_tlps_tenant_id", table_name="trade_lifecycle_projection_state")
    op.drop_index("ix_tlps_tenant_dirty", table_name="trade_lifecycle_projection_state")
    op.drop_index("ix_tlps_id", table_name="trade_lifecycle_projection_state")
    op.drop_table("trade_lifecycle_projection_state")
