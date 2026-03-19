"""Add tenant identity foundation and tenant ownership columns

Revision ID: 8b7c6d5e4f31
Revises: f2a6c4b9e1d7
Create Date: 2026-03-18 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b7c6d5e4f31"
down_revision: Union[str, None] = "f2a6c4b9e1d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_TENANT_ID = 1


def _exec(sql: str, params: dict[str, object] | None = None) -> None:
    bind = op.get_bind()
    bind.execute(sa.text(sql), params or {})


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=False)

    _exec(
        "INSERT INTO tenants (id, slug, name, is_active) "
        "SELECT :id, :slug, :name, TRUE "
        "WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE id = :id)",
        {"id": DEFAULT_TENANT_ID, "slug": "default", "name": "Default Tenant"},
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"], unique=False)
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"], unique=False)
    op.create_index("ix_memberships_user_tenant", "memberships", ["user_id", "tenant_id"], unique=False)

    _exec(
        "INSERT INTO memberships (tenant_id, user_id, role, is_active) "
        "SELECT :tenant_id, u.id, 'owner', TRUE "
        "FROM users u "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM memberships m "
        "  WHERE m.tenant_id = :tenant_id AND m.user_id = u.id"
        ")",
        {"tenant_id": DEFAULT_TENANT_ID},
    )

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("tenant_id", sa.Integer(), nullable=True, server_default=sa.text(str(DEFAULT_TENANT_ID)))
        )

    _exec("UPDATE trades SET tenant_id = :tenant_id WHERE tenant_id IS NULL", {"tenant_id": DEFAULT_TENANT_ID})

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key("fk_trades_tenant_id", "tenants", ["tenant_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_unique_constraint("uq_trades_id_tenant", ["id", "tenant_id"])
        batch_op.drop_index("ix_trades_symbol_entry_date")
        batch_op.drop_index("ix_trades_status")
        batch_op.create_index("ix_trades_tenant_symbol_entry_date", ["tenant_id", "symbol", "entry_date"], unique=False)
        batch_op.create_index("ix_trades_tenant_status", ["tenant_id", "status"], unique=False)
        batch_op.create_index("ix_trades_tenant_id", ["tenant_id"], unique=False)

    op.create_table(
        "trade_fills_new",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default=sa.text(str(DEFAULT_TENANT_ID))),
        sa.Column("fill_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("commission", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("external_fill_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trade_id", "tenant_id"], ["trades.id", "trades.tenant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "external_fill_id", name="uq_trade_fills_tenant_external_fill_id"),
    )

    _exec(
        "INSERT INTO trade_fills_new ("
        "id, trade_id, tenant_id, fill_datetime, side, quantity, price, commission, source, external_fill_id, created_at"
        ") "
        "SELECT "
        "id, trade_id, :tenant_id, fill_datetime, side, quantity, price, commission, source, external_fill_id, created_at "
        "FROM trade_fills",
        {"tenant_id": DEFAULT_TENANT_ID},
    )

    op.drop_table("trade_fills")
    op.rename_table("trade_fills_new", "trade_fills")

    op.create_index("ix_trade_fills_id", "trade_fills", ["id"], unique=False)
    op.create_index("ix_trade_fills_trade_id", "trade_fills", ["trade_id"], unique=False)
    op.create_index("ix_trade_fills_tenant_id", "trade_fills", ["tenant_id"], unique=False)
    op.create_index(
        "ix_trade_fills_tenant_trade_fill_datetime",
        "trade_fills",
        ["tenant_id", "trade_id", "fill_datetime"],
        unique=False,
    )


def downgrade() -> None:
    op.create_table(
        "trade_fills_old",
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

    _exec(
        "INSERT INTO trade_fills_old ("
        "id, trade_id, fill_datetime, side, quantity, price, commission, source, external_fill_id, created_at"
        ") "
        "SELECT "
        "tf.id, tf.trade_id, tf.fill_datetime, tf.side, tf.quantity, tf.price, tf.commission, tf.source, "
        "CASE "
        "  WHEN tf.external_fill_id IS NULL THEN NULL "
        "  WHEN EXISTS ("
        "    SELECT 1 FROM trade_fills tf2 "
        "    WHERE tf2.external_fill_id = tf.external_fill_id AND tf2.id < tf.id"
        "  ) THEN NULL "
        "  ELSE tf.external_fill_id "
        "END AS external_fill_id, "
        "tf.created_at "
        "FROM trade_fills tf"
    )

    op.drop_table("trade_fills")
    op.rename_table("trade_fills_old", "trade_fills")

    op.create_index("ix_trade_fills_trade_id", "trade_fills", ["trade_id"], unique=False)
    op.create_index("ix_trade_fills_id", "trade_fills", ["id"], unique=False)
    op.create_index(
        "ix_trade_fills_trade_id_fill_datetime",
        "trade_fills",
        ["trade_id", "fill_datetime"],
        unique=False,
    )

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.drop_index("ix_trades_tenant_id")
        batch_op.drop_index("ix_trades_tenant_status")
        batch_op.drop_index("ix_trades_tenant_symbol_entry_date")
        batch_op.create_index("ix_trades_status", ["status"], unique=False)
        batch_op.create_index("ix_trades_symbol_entry_date", ["symbol", "entry_date"], unique=False)
        batch_op.drop_constraint("uq_trades_id_tenant", type_="unique")
        batch_op.drop_constraint("fk_trades_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    op.drop_index("ix_memberships_user_tenant", table_name="memberships")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_tenant_id", table_name="memberships")
    op.drop_table("memberships")

    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
