from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from tests.utils.alembic_helpers import get_head_revision

TENANT_FOUNDATION_REVISION = "8b7c6d5e4f31"
PRE_TENANT_REVISION = "f2a6c4b9e1d7"


def _run_alembic(repo_root: Path, env: dict[str, str], *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_backfill_adopts_legacy_rows_to_default_tenant(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "backfill_adopt_legacy.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    _run_alembic(repo_root, env, "upgrade", PRE_TENANT_REVISION)

    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO users (username, email, password_hash) VALUES ('legacy', 'legacy@example.com', 'x')")
        user_id = conn.execute("SELECT id FROM users WHERE username = 'legacy'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO trades (
                user_id, symbol, direction, status, created_at, updated_at
            ) VALUES (?, 'AAPL', 'LONG', 'open', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (user_id,),
        )
        trade_id = conn.execute("SELECT id FROM trades ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.execute(
            """
            INSERT INTO trade_fills (
                trade_id, fill_datetime, side, quantity, price, commission, source, external_fill_id
            ) VALUES (?, CURRENT_TIMESTAMP, 'BUY', 1, 100, 0, 'manual', 'legacy-fill')
            """,
            (trade_id,),
        )
        conn.commit()

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        tenant = conn.execute("SELECT id, slug, name FROM tenants WHERE id = 1").fetchone()
        trade_tenant = conn.execute("SELECT tenant_id FROM trades WHERE id = ?", (trade_id,)).fetchone()[0]
        fill_tenant = conn.execute("SELECT tenant_id FROM trade_fills WHERE trade_id = ?", (trade_id,)).fetchone()[0]
        membership = conn.execute(
            "SELECT tenant_id, user_id, role FROM memberships WHERE tenant_id = 1 AND user_id = ?",
            (user_id,),
        ).fetchone()
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert tenant == (1, "default", "Default Tenant")
    assert trade_tenant == 1
    assert fill_tenant == 1
    assert membership == (1, user_id, "owner")
    assert revision == get_head_revision()


def test_backfill_bootstraps_default_admin_when_users_empty(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "backfill_bootstrap_admin.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        users = conn.execute("SELECT id, username, email FROM users ORDER BY id").fetchall()
        memberships = conn.execute(
            "SELECT tenant_id, user_id, role FROM memberships ORDER BY user_id"
        ).fetchall()

    assert len(users) == 1
    assert users[0][1] == "bootstrap_admin"
    assert users[0][2] == "bootstrap-admin@local.invalid"
    assert memberships == [(1, users[0][0], "owner")]


def test_backfill_aligns_fill_tenant_to_parent_trade(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "backfill_align_fill_tenant.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    _run_alembic(repo_root, env, "upgrade", TENANT_FOUNDATION_REVISION)

    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO users (username, email, password_hash) VALUES ('u1', 'u1@x.com', 'x')")
        conn.execute("INSERT INTO users (username, email, password_hash) VALUES ('u2', 'u2@x.com', 'x')")
        u2 = conn.execute("SELECT id FROM users WHERE username='u2'").fetchone()[0]

        conn.execute("INSERT INTO tenants (id, slug, name, is_active) VALUES (2, 'team-2', 'Team 2', 1)")
        conn.execute("INSERT INTO memberships (tenant_id, user_id, role, is_active) VALUES (2, ?, 'owner', 1)", (u2,))

        conn.execute(
            "INSERT INTO trades (tenant_id, user_id, symbol, direction, status) VALUES (2, ?, 'MSFT', 'LONG', 'open')",
            (u2,),
        )
        trade_id = conn.execute("SELECT id FROM trades WHERE tenant_id=2 ORDER BY id DESC LIMIT 1").fetchone()[0]

        # Intentional legacy mismatch: fill points to trade in tenant 2 but stores tenant 1.
        conn.execute(
            """
            INSERT INTO trade_fills (
                trade_id, tenant_id, fill_datetime, side, quantity, price, commission, source, external_fill_id
            ) VALUES (?, 1, CURRENT_TIMESTAMP, 'BUY', 1, 10, 0, 'manual', NULL)
            """,
            (trade_id,),
        )
        fill_id = conn.execute("SELECT id FROM trade_fills ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.commit()

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        aligned_tenant = conn.execute("SELECT tenant_id FROM trade_fills WHERE id = ?", (fill_id,)).fetchone()[0]

    assert aligned_tenant == 2
