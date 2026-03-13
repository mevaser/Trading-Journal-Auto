"""Add missing duration_days column to trades

Revision ID: f2a6c4b9e1d7
Revises: c1b9f2a7d115
Create Date: 2026-03-09 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a6c4b9e1d7"
down_revision: Union[str, None] = "c1b9f2a7d115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.add_column(sa.Column("duration_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.drop_column("duration_days")
