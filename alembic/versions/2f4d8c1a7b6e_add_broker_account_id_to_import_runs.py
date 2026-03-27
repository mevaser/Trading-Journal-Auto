"""Add broker_account_id to import_runs

Revision ID: 2f4d8c1a7b6e
Revises: 7c3e1b2a9d4f
Create Date: 2026-03-24 13:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2f4d8c1a7b6e"
down_revision: Union[str, None] = "7c3e1b2a9d4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("import_runs", sa.Column("broker_account_id", sa.String(length=120), nullable=True))
    op.create_index(op.f("ix_import_runs_broker_account_id"), "import_runs", ["broker_account_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_import_runs_broker_account_id"), table_name="import_runs")
    op.drop_column("import_runs", "broker_account_id")
