"""Backfill legacy ownership and bootstrap default tenant admin mapping

Revision ID: b91e4c2d7a10
Revises: 8b7c6d5e4f31
Create Date: 2026-03-18 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b91e4c2d7a10"
down_revision: Union[str, None] = "8b7c6d5e4f31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_TENANT_ID = 1
DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default Tenant"
BOOTSTRAP_ADMIN_USERNAME = "bootstrap_admin"
BOOTSTRAP_ADMIN_EMAIL = "bootstrap-admin@local.invalid"
BOOTSTRAP_ADMIN_PASSWORD_HASH = "!bootstrap-password-reset-required!"


def _exec(sql: str, params: dict[str, object] | None = None) -> None:
    op.get_bind().execute(sa.text(sql), params or {})


def _scalar(sql: str, params: dict[str, object] | None = None) -> object | None:
    return op.get_bind().execute(sa.text(sql), params or {}).scalar()


def upgrade() -> None:
    # Ensure deterministic default tenant identity for legacy adoption.
    _exec(
        "INSERT INTO tenants (id, slug, name, is_active) "
        "SELECT :id, :slug, :name, TRUE "
        "WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE id = :id)",
        {"id": DEFAULT_TENANT_ID, "slug": DEFAULT_TENANT_SLUG, "name": DEFAULT_TENANT_NAME},
    )

    # Bootstrap one admin-like user if the database has no users yet.
    user_count = int(_scalar("SELECT COUNT(*) FROM users") or 0)
    if user_count == 0:
        _exec(
            "INSERT INTO users (username, email, password_hash) "
            "VALUES (:username, :email, :password_hash)",
            {
                "username": BOOTSTRAP_ADMIN_USERNAME,
                "email": BOOTSTRAP_ADMIN_EMAIL,
                "password_hash": BOOTSTRAP_ADMIN_PASSWORD_HASH,
            },
        )

    owner_user_id = _scalar("SELECT id FROM users ORDER BY id ASC LIMIT 1")

    # Ensure every user is linked to the default tenant with deterministic role assignment.
    # Existing memberships are preserved; only missing links are created.
    _exec(
        "INSERT INTO memberships (tenant_id, user_id, role, is_active) "
        "SELECT :tenant_id, u.id, "
        "CASE WHEN u.id = :owner_user_id THEN 'owner' ELSE 'member' END, TRUE "
        "FROM users u "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM memberships m "
        "  WHERE m.tenant_id = :tenant_id AND m.user_id = u.id"
        ")",
        {"tenant_id": DEFAULT_TENANT_ID, "owner_user_id": owner_user_id},
    )

    # Deterministically adopt orphan/invalid ownership onto default tenant.
    _exec(
        "UPDATE trades SET tenant_id = :tenant_id "
        "WHERE tenant_id IS NULL "
        "   OR NOT EXISTS (SELECT 1 FROM tenants t WHERE t.id = trades.tenant_id)",
        {"tenant_id": DEFAULT_TENANT_ID},
    )

    # Align fills to their parent trade tenant when safe.
    _exec(
        "UPDATE trade_fills "
        "SET tenant_id = (SELECT t.tenant_id FROM trades t WHERE t.id = trade_fills.trade_id) "
        "WHERE EXISTS ("
        "  SELECT 1 FROM trades t "
        "  WHERE t.id = trade_fills.trade_id "
        "    AND t.tenant_id <> trade_fills.tenant_id"
        ") "
        "AND ("
        "  trade_fills.external_fill_id IS NULL "
        "  OR NOT EXISTS ("
        "    SELECT 1 FROM trade_fills tf2 "
        "    WHERE tf2.id <> trade_fills.id "
        "      AND tf2.tenant_id = (SELECT t2.tenant_id FROM trades t2 WHERE t2.id = trade_fills.trade_id) "
        "      AND tf2.external_fill_id = trade_fills.external_fill_id"
        "  )"
        ")"
    )

    # Remaining orphan/invalid fill tenant ownership falls back to default tenant when safe.
    _exec(
        "UPDATE trade_fills "
        "SET tenant_id = :tenant_id "
        "WHERE ("
        "  tenant_id IS NULL "
        "  OR NOT EXISTS (SELECT 1 FROM tenants t WHERE t.id = trade_fills.tenant_id)"
        ") "
        "AND ("
        "  external_fill_id IS NULL "
        "  OR NOT EXISTS ("
        "    SELECT 1 FROM trade_fills tf2 "
        "    WHERE tf2.id <> trade_fills.id "
        "      AND tf2.tenant_id = :tenant_id "
        "      AND tf2.external_fill_id = trade_fills.external_fill_id"
        "  )"
        ")",
        {"tenant_id": DEFAULT_TENANT_ID},
    )


def downgrade() -> None:
    # Best-effort rollback for bootstrap user only.
    # Ownership remapping is intentionally not reversed to avoid destructive data rewrites.
    _exec(
        "DELETE FROM memberships "
        "WHERE tenant_id = :tenant_id "
        "  AND user_id IN ("
        "    SELECT id FROM users "
        "    WHERE username = :username AND email = :email AND password_hash = :password_hash"
        "  )",
        {
            "tenant_id": DEFAULT_TENANT_ID,
            "username": BOOTSTRAP_ADMIN_USERNAME,
            "email": BOOTSTRAP_ADMIN_EMAIL,
            "password_hash": BOOTSTRAP_ADMIN_PASSWORD_HASH,
        },
    )

    _exec(
        "DELETE FROM users "
        "WHERE username = :username "
        "  AND email = :email "
        "  AND password_hash = :password_hash "
        "  AND NOT EXISTS (SELECT 1 FROM trades WHERE trades.user_id = users.id)",
        {
            "username": BOOTSTRAP_ADMIN_USERNAME,
            "email": BOOTSTRAP_ADMIN_EMAIL,
            "password_hash": BOOTSTRAP_ADMIN_PASSWORD_HASH,
        },
    )
