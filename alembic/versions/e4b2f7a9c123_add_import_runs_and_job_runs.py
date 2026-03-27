"""Add import_runs and job_runs audit tables

Revision ID: e4b2f7a9c123
Revises: d3c1a9f4e6b2
Create Date: 2026-03-20 12:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e4b2f7a9c123"
down_revision: Union[str, None] = "d3c1a9f4e6b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="ibkr", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_id", sa.String(length=120), nullable=True),
        sa.Column("total_received", sa.Integer(), server_default="0", nullable=False),
        sa.Column("imported", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicates_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("trades_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("trades_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_import_runs_status_valid",
        ),
        sa.CheckConstraint("total_received >= 0", name="ck_import_runs_total_received_non_negative"),
        sa.CheckConstraint("imported >= 0", name="ck_import_runs_imported_non_negative"),
        sa.CheckConstraint(
            "duplicates_skipped >= 0",
            name="ck_import_runs_duplicates_skipped_non_negative",
        ),
        sa.CheckConstraint("failed >= 0", name="ck_import_runs_failed_non_negative"),
        sa.CheckConstraint(
            "trades_created >= 0",
            name="ck_import_runs_trades_created_non_negative",
        ),
        sa.CheckConstraint(
            "trades_updated >= 0",
            name="ck_import_runs_trades_updated_non_negative",
        ),
        sa.CheckConstraint("error_count >= 0", name="ck_import_runs_error_count_non_negative"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_import_runs_id"), "import_runs", ["id"], unique=False)
    op.create_index(op.f("ix_import_runs_job_id"), "import_runs", ["job_id"], unique=False)
    op.create_index("ix_import_runs_tenant_created_at", "import_runs", ["tenant_id", "created_at"], unique=False)
    op.create_index(op.f("ix_import_runs_tenant_id"), "import_runs", ["tenant_id"], unique=False)

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("import_run_id", sa.Integer(), nullable=True),
        sa.Column("job_type", sa.String(length=32), server_default="ibkr_import", nullable=False),
        sa.Column("provider", sa.String(length=16), server_default="celery", nullable=False),
        sa.Column("external_job_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_job_runs_status_valid",
        ),
        sa.ForeignKeyConstraint(["import_run_id"], ["import_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_job_id"),
    )
    op.create_index(op.f("ix_job_runs_external_job_id"), "job_runs", ["external_job_id"], unique=True)
    op.create_index(op.f("ix_job_runs_id"), "job_runs", ["id"], unique=False)
    op.create_index(op.f("ix_job_runs_import_run_id"), "job_runs", ["import_run_id"], unique=False)
    op.create_index("ix_job_runs_tenant_status_created_at", "job_runs", ["tenant_id", "status", "created_at"], unique=False)
    op.create_index(op.f("ix_job_runs_tenant_id"), "job_runs", ["tenant_id"], unique=False)

    with op.batch_alter_table("trade_fills", schema=None) as batch_op:
        batch_op.drop_constraint("uq_trade_fills_tenant_external_fill_id", type_="unique")
        batch_op.create_unique_constraint(
            "uq_trade_fills_tenant_source_external_fill_id",
            ["tenant_id", "source", "external_fill_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("trade_fills", schema=None) as batch_op:
        batch_op.drop_constraint("uq_trade_fills_tenant_source_external_fill_id", type_="unique")
        batch_op.create_unique_constraint(
            "uq_trade_fills_tenant_external_fill_id",
            ["tenant_id", "external_fill_id"],
        )

    op.drop_index(op.f("ix_job_runs_tenant_id"), table_name="job_runs")
    op.drop_index("ix_job_runs_tenant_status_created_at", table_name="job_runs")
    op.drop_index(op.f("ix_job_runs_import_run_id"), table_name="job_runs")
    op.drop_index(op.f("ix_job_runs_id"), table_name="job_runs")
    op.drop_index(op.f("ix_job_runs_external_job_id"), table_name="job_runs")
    op.drop_table("job_runs")

    op.drop_index(op.f("ix_import_runs_tenant_id"), table_name="import_runs")
    op.drop_index("ix_import_runs_tenant_created_at", table_name="import_runs")
    op.drop_index(op.f("ix_import_runs_job_id"), table_name="import_runs")
    op.drop_index(op.f("ix_import_runs_id"), table_name="import_runs")
    op.drop_table("import_runs")
