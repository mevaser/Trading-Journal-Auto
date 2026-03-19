"""Harden trade/fill constraints and add performance indexes

Revision ID: d3c1a9f4e6b2
Revises: b91e4c2d7a10
Create Date: 2026-03-19 12:25:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3c1a9f4e6b2"
down_revision: Union[str, None] = "b91e4c2d7a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _exec(sql: str, params: dict[str, object] | None = None) -> None:
    op.get_bind().execute(sa.text(sql), params or {})


def upgrade() -> None:
    # Normalize legacy data so new integrity checks can be applied safely.
    _exec("UPDATE trades SET direction = UPPER(TRIM(direction)) WHERE direction IS NOT NULL")
    _exec(
        "UPDATE trades SET direction = 'LONG' "
        "WHERE direction IS NULL OR direction NOT IN ('LONG', 'SHORT')"
    )

    _exec("UPDATE trades SET status = LOWER(TRIM(status)) WHERE status IS NOT NULL")
    _exec(
        "UPDATE trades SET status = 'open' "
        "WHERE status IS NULL OR status NOT IN ('open', 'partial', 'closed')"
    )

    _exec(
        "UPDATE trades SET closed_at = opened_at "
        "WHERE opened_at IS NOT NULL AND closed_at IS NOT NULL AND closed_at < opened_at"
    )
    _exec("UPDATE trades SET quantity_opened = ABS(quantity_opened) WHERE quantity_opened < 0")
    _exec("UPDATE trades SET quantity_closed = ABS(quantity_closed) WHERE quantity_closed < 0")
    _exec("UPDATE trades SET remaining_quantity = 0 WHERE remaining_quantity < 0")
    _exec("UPDATE trades SET duration_days = 0 WHERE duration_days < 0")

    _exec("UPDATE trade_fills SET side = UPPER(TRIM(side)) WHERE side IS NOT NULL")
    _exec(
        "UPDATE trade_fills SET side = 'BUY' "
        "WHERE side IS NULL OR side NOT IN ('BUY', 'SELL')"
    )
    _exec("UPDATE trade_fills SET quantity = 0.00000001 WHERE quantity <= 0")
    _exec("UPDATE trade_fills SET price = 0.0001 WHERE price <= 0")
    _exec("UPDATE trade_fills SET commission = ABS(commission) WHERE commission < 0")
    _exec(
        "UPDATE trade_fills SET source = 'manual' "
        "WHERE source IS NULL OR LENGTH(TRIM(source)) = 0"
    )
    _exec(
        "UPDATE trade_fills SET source = LOWER(TRIM(source)) "
        "WHERE source IS NOT NULL AND LENGTH(TRIM(source)) > 0"
    )
    _exec(
        "UPDATE trade_fills SET external_fill_id = NULL "
        "WHERE external_fill_id IS NOT NULL AND LENGTH(TRIM(external_fill_id)) = 0"
    )

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_trades_direction_valid",
            "direction IN ('LONG', 'SHORT')",
        )
        batch_op.create_check_constraint(
            "ck_trades_status_valid",
            "status IN ('open', 'partial', 'closed')",
        )
        batch_op.create_check_constraint(
            "ck_trades_closed_at_after_opened_at",
            "opened_at IS NULL OR closed_at IS NULL OR closed_at >= opened_at",
        )
        batch_op.create_check_constraint(
            "ck_trades_quantity_opened_non_negative",
            "quantity_opened IS NULL OR quantity_opened >= 0",
        )
        batch_op.create_check_constraint(
            "ck_trades_quantity_closed_non_negative",
            "quantity_closed IS NULL OR quantity_closed >= 0",
        )
        batch_op.create_check_constraint(
            "ck_trades_remaining_quantity_non_negative",
            "remaining_quantity IS NULL OR remaining_quantity >= 0",
        )
        batch_op.create_check_constraint(
            "ck_trades_duration_days_non_negative",
            "duration_days IS NULL OR duration_days >= 0",
        )

    op.create_index(
        "ix_trades_tenant_created_at_id",
        "trades",
        ["tenant_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_trades_tenant_opened_at",
        "trades",
        ["tenant_id", "opened_at"],
        unique=False,
    )
    op.create_index(
        "ix_trades_tenant_strategy_opened_at",
        "trades",
        ["tenant_id", "strategy", "opened_at"],
        unique=False,
    )

    with op.batch_alter_table("trade_fills", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_trade_fills_side_valid",
            "side IN ('BUY', 'SELL')",
        )
        batch_op.create_check_constraint(
            "ck_trade_fills_quantity_positive",
            "quantity > 0",
        )
        batch_op.create_check_constraint(
            "ck_trade_fills_price_positive",
            "price > 0",
        )
        batch_op.create_check_constraint(
            "ck_trade_fills_commission_non_negative",
            "commission IS NULL OR commission >= 0",
        )
        batch_op.create_check_constraint(
            "ck_trade_fills_source_non_empty",
            "length(trim(source)) > 0",
        )
        batch_op.create_check_constraint(
            "ck_trade_fills_external_fill_id_non_empty",
            "external_fill_id IS NULL OR length(trim(external_fill_id)) > 0",
        )

    op.create_index(
        "ix_trade_fills_trade_fill_datetime",
        "trade_fills",
        ["trade_id", "fill_datetime"],
        unique=False,
    )
    op.create_index(
        "ix_trade_fills_tenant_fill_datetime",
        "trade_fills",
        ["tenant_id", "fill_datetime"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trade_fills_tenant_fill_datetime", table_name="trade_fills")
    op.drop_index("ix_trade_fills_trade_fill_datetime", table_name="trade_fills")

    with op.batch_alter_table("trade_fills", schema=None) as batch_op:
        batch_op.drop_constraint("ck_trade_fills_external_fill_id_non_empty", type_="check")
        batch_op.drop_constraint("ck_trade_fills_source_non_empty", type_="check")
        batch_op.drop_constraint("ck_trade_fills_commission_non_negative", type_="check")
        batch_op.drop_constraint("ck_trade_fills_price_positive", type_="check")
        batch_op.drop_constraint("ck_trade_fills_quantity_positive", type_="check")
        batch_op.drop_constraint("ck_trade_fills_side_valid", type_="check")

    op.drop_index("ix_trades_tenant_strategy_opened_at", table_name="trades")
    op.drop_index("ix_trades_tenant_opened_at", table_name="trades")
    op.drop_index("ix_trades_tenant_created_at_id", table_name="trades")

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.drop_constraint("ck_trades_duration_days_non_negative", type_="check")
        batch_op.drop_constraint("ck_trades_remaining_quantity_non_negative", type_="check")
        batch_op.drop_constraint("ck_trades_quantity_closed_non_negative", type_="check")
        batch_op.drop_constraint("ck_trades_quantity_opened_non_negative", type_="check")
        batch_op.drop_constraint("ck_trades_closed_at_after_opened_at", type_="check")
        batch_op.drop_constraint("ck_trades_status_valid", type_="check")
        batch_op.drop_constraint("ck_trades_direction_valid", type_="check")
