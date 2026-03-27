"""Add canonical ingestion tables for broker executions

Revision ID: 9a7d1c2b4e8f
Revises: e4b2f7a9c123
Create Date: 2026-03-22 15:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a7d1c2b4e8f"
down_revision: Union[str, None] = "e4b2f7a9c123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broker_execution_fills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("import_run_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="ibkr", nullable=False),
        sa.Column("broker_account_id", sa.String(length=120), nullable=False),
        sa.Column("external_execution_id", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("commission", sa.Numeric(precision=18, scale=8), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("execution_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload_json", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("supersedes_execution_fill_id", sa.Integer(), nullable=True),
        sa.Column("superseded_by_execution_fill_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_broker_execution_fills_side_valid"),
        sa.CheckConstraint("quantity > 0", name="ck_broker_execution_fills_quantity_positive"),
        sa.CheckConstraint("price > 0", name="ck_broker_execution_fills_price_positive"),
        sa.CheckConstraint("commission >= 0", name="ck_broker_execution_fills_commission_non_negative"),
        sa.CheckConstraint("length(trim(source)) > 0", name="ck_broker_execution_fills_source_non_empty"),
        sa.CheckConstraint(
            "length(trim(broker_account_id)) > 0",
            name="ck_broker_execution_fills_broker_account_non_empty",
        ),
        sa.CheckConstraint(
            "length(trim(external_execution_id)) > 0",
            name="ck_broker_execution_fills_external_execution_non_empty",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["import_run_id"], ["import_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["supersedes_execution_fill_id"],
            ["broker_execution_fills.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_execution_fill_id"],
            ["broker_execution_fills.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_broker_execution_fills_id"), "broker_execution_fills", ["id"], unique=False)
    op.create_index(
        "ix_broker_execution_fills_identity_lookup",
        "broker_execution_fills",
        ["tenant_id", "source", "broker_account_id", "external_execution_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_broker_execution_fills_identity_active_unique",
        "broker_execution_fills",
        ["tenant_id", "source", "broker_account_id", "external_execution_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "ix_broker_execution_fills_tenant_symbol_time",
        "broker_execution_fills",
        ["tenant_id", "symbol", "execution_time_utc", "id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_broker_execution_fills_tenant_id"),
        "broker_execution_fills",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_broker_execution_fills_import_run_id"),
        "broker_execution_fills",
        ["import_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_broker_execution_fills_supersedes_execution_fill_id"),
        "broker_execution_fills",
        ["supersedes_execution_fill_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_broker_execution_fills_superseded_by_execution_fill_id"),
        "broker_execution_fills",
        ["superseded_by_execution_fill_id"],
        unique=False,
    )
    op.create_index(
        "ix_broker_execution_fills_payload_hash",
        "broker_execution_fills",
        ["payload_hash"],
        unique=False,
    )

    op.create_table(
        "import_run_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("import_run_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("record_seq", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("broker_account_id", sa.String(length=120), nullable=True),
        sa.Column("external_execution_id", sa.String(length=120), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("side", sa.String(length=4), nullable=True),
        sa.Column("asset_type", sa.String(length=20), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("commission", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("execution_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("raw_payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="staged", nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("canonical_execution_fill_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('staged', 'duplicate_skipped', 'resolved_inserted', 'resolved_superseded', 'failed_validation', 'failed_processing')",
            name="ck_import_run_records_status_valid",
        ),
        sa.CheckConstraint("record_seq > 0", name="ck_import_run_records_record_seq_positive"),
        sa.ForeignKeyConstraint(["import_run_id"], ["import_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["canonical_execution_fill_id"],
            ["broker_execution_fills.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_run_id", "record_seq", name="uq_import_run_records_import_run_record_seq"),
    )

    op.create_index(op.f("ix_import_run_records_id"), "import_run_records", ["id"], unique=False)
    op.create_index(
        "ix_import_run_records_tenant_run_status",
        "import_run_records",
        ["tenant_id", "import_run_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_import_run_records_identity_lookup",
        "import_run_records",
        ["tenant_id", "source", "broker_account_id", "external_execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_run_records_import_run_id"),
        "import_run_records",
        ["import_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_run_records_tenant_id"),
        "import_run_records",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_run_records_canonical_execution_fill_id"),
        "import_run_records",
        ["canonical_execution_fill_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_import_run_records_canonical_execution_fill_id"), table_name="import_run_records")
    op.drop_index(op.f("ix_import_run_records_tenant_id"), table_name="import_run_records")
    op.drop_index(op.f("ix_import_run_records_import_run_id"), table_name="import_run_records")
    op.drop_index("ix_import_run_records_identity_lookup", table_name="import_run_records")
    op.drop_index("ix_import_run_records_tenant_run_status", table_name="import_run_records")
    op.drop_index(op.f("ix_import_run_records_id"), table_name="import_run_records")
    op.drop_table("import_run_records")

    op.drop_index(op.f("ix_broker_execution_fills_superseded_by_execution_fill_id"), table_name="broker_execution_fills")
    op.drop_index(op.f("ix_broker_execution_fills_supersedes_execution_fill_id"), table_name="broker_execution_fills")
    op.drop_index(op.f("ix_broker_execution_fills_import_run_id"), table_name="broker_execution_fills")
    op.drop_index(op.f("ix_broker_execution_fills_tenant_id"), table_name="broker_execution_fills")
    op.drop_index("ix_broker_execution_fills_payload_hash", table_name="broker_execution_fills")
    op.drop_index("ix_broker_execution_fills_tenant_symbol_time", table_name="broker_execution_fills")
    op.drop_index("ix_broker_execution_fills_identity_active_unique", table_name="broker_execution_fills")
    op.drop_index("ix_broker_execution_fills_identity_lookup", table_name="broker_execution_fills")
    op.drop_index(op.f("ix_broker_execution_fills_id"), table_name="broker_execution_fills")
    op.drop_table("broker_execution_fills")
