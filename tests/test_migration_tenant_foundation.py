from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from tests.utils.alembic_helpers import get_head_revision


def _run_alembic(repo_root: Path, env: dict[str, str], *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_tenant_foundation_upgrade_has_expected_schema(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "tenant_foundation_upgrade.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        trade_columns = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(trades)")}
        fill_columns = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(trade_fills)")}
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]

        trade_indexes = {row[1] for row in conn.execute("PRAGMA index_list(trades)")}
        fill_indexes = {row[1] for row in conn.execute("PRAGMA index_list(trade_fills)")}

        unique_index_name = None
        for row in conn.execute("PRAGMA index_list(trade_fills)"):
            if row[1] == "sqlite_autoindex_trade_fills_1" or row[2] == 1:
                cols = [c[2] for c in conn.execute(f"PRAGMA index_info({row[1]!r})")]
                if cols == ["tenant_id", "source", "external_fill_id"]:
                    unique_index_name = row[1]
                    break

        default_tenant = conn.execute("SELECT id, slug FROM tenants WHERE id = 1").fetchone()

    assert {"tenants", "memberships", "trades", "trade_fills"}.issubset(tables)
    assert "tenant_id" in trade_columns and trade_columns["tenant_id"] == 1
    assert "tenant_id" in fill_columns and fill_columns["tenant_id"] == 1
    assert "ix_trades_tenant_symbol_entry_date" in trade_indexes
    assert "ix_trades_tenant_status" in trade_indexes
    assert "ix_trade_fills_tenant_trade_fill_datetime" in fill_indexes
    assert unique_index_name is not None
    assert default_tenant == (1, "default")
    assert revision == get_head_revision()


def test_tenant_foundation_downgrade_handles_cross_tenant_external_fill_id_duplicates(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = (tmp_path / "tenant_foundation_downgrade.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO users (username, email, password_hash) VALUES ('u1', 'u1@example.com', 'x')")
        conn.execute("INSERT INTO users (username, email, password_hash) VALUES ('u2', 'u2@example.com', 'x')")
        u1 = conn.execute("SELECT id FROM users WHERE username = 'u1'").fetchone()[0]
        u2 = conn.execute("SELECT id FROM users WHERE username = 'u2'").fetchone()[0]

        conn.execute("INSERT INTO tenants (id, slug, name, is_active) VALUES (2, 't2', 'Tenant 2', 1)")
        conn.execute("INSERT INTO memberships (tenant_id, user_id, role, is_active) VALUES (1, ?, 'owner', 1)", (u1,))
        conn.execute("INSERT INTO memberships (tenant_id, user_id, role, is_active) VALUES (2, ?, 'owner', 1)", (u2,))

        conn.execute(
            "INSERT INTO trades (tenant_id, user_id, symbol, direction, status) VALUES (1, ?, 'AAPL', 'LONG', 'open')",
            (u1,),
        )
        conn.execute(
            "INSERT INTO trades (tenant_id, user_id, symbol, direction, status) VALUES (2, ?, 'AAPL', 'LONG', 'open')",
            (u2,),
        )
        t1 = conn.execute("SELECT id FROM trades WHERE tenant_id = 1 ORDER BY id DESC LIMIT 1").fetchone()[0]
        t2 = conn.execute("SELECT id FROM trades WHERE tenant_id = 2 ORDER BY id DESC LIMIT 1").fetchone()[0]

        conn.execute(
            """
            INSERT INTO trade_fills (
                trade_id, tenant_id, fill_datetime, side, quantity, price, commission, source, external_fill_id
            ) VALUES (?, 1, CURRENT_TIMESTAMP, 'BUY', 1, 100, 0, 'manual', 'dup-fill')
            """,
            (t1,),
        )
        conn.execute(
            """
            INSERT INTO trade_fills (
                trade_id, tenant_id, fill_datetime, side, quantity, price, commission, source, external_fill_id
            ) VALUES (?, 2, CURRENT_TIMESTAMP, 'BUY', 1, 100, 0, 'manual', 'dup-fill')
            """,
            (t2,),
        )
        conn.commit()

    _run_alembic(repo_root, env, "downgrade", "f2a6c4b9e1d7")

    with sqlite3.connect(db_path) as conn:
        tables_after_downgrade = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows = conn.execute(
            "SELECT external_fill_id FROM trade_fills WHERE external_fill_id = 'dup-fill'"
        ).fetchall()

    assert "tenants" not in tables_after_downgrade
    assert "memberships" not in tables_after_downgrade
    assert len(rows) == 1

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert revision == get_head_revision()
