"""Add trade fill model and position metadata

Revision ID: c1b9f2a7d115
Revises: 489442fdcc53
Create Date: 2026-03-06 09:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1b9f2a7d115"
down_revision: Union[str, None] = "489442fdcc53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.alter_column("entry_date", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch_op.alter_column("entry_price", existing_type=sa.Numeric(precision=10, scale=4), nullable=True)
        batch_op.alter_column("quantity", existing_type=sa.Numeric(precision=18, scale=8), nullable=True)

        batch_op.add_column(sa.Column("asset_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("thesis", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("notes", sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column("tags", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("status", sa.String(length=10), nullable=False, server_default="open"))
        batch_op.add_column(sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("avg_entry_price", sa.Numeric(precision=10, scale=4), nullable=True))
        batch_op.add_column(sa.Column("avg_exit_price", sa.Numeric(precision=10, scale=4), nullable=True))
        batch_op.add_column(sa.Column("quantity_opened", sa.Numeric(precision=18, scale=8), nullable=True))
        batch_op.add_column(sa.Column("quantity_closed", sa.Numeric(precision=18, scale=8), nullable=True))
        batch_op.add_column(sa.Column("remaining_quantity", sa.Numeric(precision=18, scale=8), nullable=True))
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.create_index("ix_trades_status", ["status"], unique=False)

    op.create_table(
        "trade_fills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("fill_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("commission", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("external_fill_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_fill_id"),
    )
    op.create_index("ix_trade_fills_trade_id", "trade_fills", ["trade_id"], unique=False)
    op.create_index("ix_trade_fills_id", "trade_fills", ["id"], unique=False)
    op.create_index(
        "ix_trade_fills_trade_id_fill_datetime",
        "trade_fills",
        ["trade_id", "fill_datetime"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trade_fills_trade_id_fill_datetime", table_name="trade_fills")
    op.drop_index("ix_trade_fills_id", table_name="trade_fills")
    op.drop_index("ix_trade_fills_trade_id", table_name="trade_fills")
    op.drop_table("trade_fills")

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.drop_index("ix_trades_status")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("remaining_quantity")
        batch_op.drop_column("quantity_closed")
        batch_op.drop_column("quantity_opened")
        batch_op.drop_column("avg_exit_price")
        batch_op.drop_column("avg_entry_price")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("opened_at")
        batch_op.drop_column("status")
        batch_op.drop_column("tags")
        batch_op.drop_column("notes")
        batch_op.drop_column("thesis")
        batch_op.drop_column("asset_type")

        batch_op.alter_column("quantity", existing_type=sa.Numeric(precision=18, scale=8), nullable=False)
        batch_op.alter_column("entry_price", existing_type=sa.Numeric(precision=10, scale=4), nullable=False)
        batch_op.alter_column("entry_date", existing_type=sa.DateTime(timezone=True), nullable=False)
