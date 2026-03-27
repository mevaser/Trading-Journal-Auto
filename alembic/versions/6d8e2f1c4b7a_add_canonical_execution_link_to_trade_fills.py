"""Add canonical execution linkage to trade_fills

Revision ID: 6d8e2f1c4b7a
Revises: 2f4d8c1a7b6e
Create Date: 2026-03-24 15:55:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6d8e2f1c4b7a"
down_revision: Union[str, None] = "2f4d8c1a7b6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trade_fills", schema=None) as batch_op:
        batch_op.add_column(sa.Column("canonical_execution_fill_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_trade_fills_canonical_execution_fill_id",
            "broker_execution_fills",
            ["canonical_execution_fill_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_index(
        op.f("ix_trade_fills_canonical_execution_fill_id"),
        "trade_fills",
        ["canonical_execution_fill_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trade_fills_canonical_execution_fill_id"), table_name="trade_fills")

    with op.batch_alter_table("trade_fills", schema=None) as batch_op:
        batch_op.drop_constraint("fk_trade_fills_canonical_execution_fill_id", type_="foreignkey")
        batch_op.drop_column("canonical_execution_fill_id")
