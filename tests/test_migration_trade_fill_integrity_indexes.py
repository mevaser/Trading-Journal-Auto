from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


HEAD_REVISION = "d3c1a9f4e6b2"


def _run_alembic(repo_root: Path, env: dict[str, str], *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_trade_fill_integrity_indexes_and_checks_exist(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "trade_fill_integrity_schema.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        trade_indexes = {row[1] for row in conn.execute("PRAGMA index_list(trades)")}
        fill_indexes = {row[1] for row in conn.execute("PRAGMA index_list(trade_fills)")}
        trades_table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='trades'"
        ).fetchone()[0]
        fills_table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='trade_fills'"
        ).fetchone()[0]
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert "ix_trades_tenant_created_at_id" in trade_indexes
    assert "ix_trades_tenant_opened_at" in trade_indexes
    assert "ix_trades_tenant_strategy_opened_at" in trade_indexes
    assert "ix_trade_fills_trade_fill_datetime" in fill_indexes
    assert "ix_trade_fills_tenant_fill_datetime" in fill_indexes

    assert "ck_trades_direction_valid" in trades_table_sql
    assert "ck_trades_status_valid" in trades_table_sql
    assert "ck_trades_closed_at_after_opened_at" in trades_table_sql
    assert "ck_trade_fills_side_valid" in fills_table_sql
    assert "ck_trade_fills_quantity_positive" in fills_table_sql
    assert "ck_trade_fills_price_positive" in fills_table_sql
    assert revision == HEAD_REVISION


def test_trade_fill_constraints_enforce_integrity(tmp_path: Path, monkeypatch) -> None:
    db_path = (tmp_path / "trade_fill_integrity_enforcement.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    _run_alembic(repo_root, env, "upgrade", "head")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        user_id = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO trades (tenant_id, user_id, symbol, direction, status) VALUES (1, ?, 'AAPL', 'LONG', 'open')",
            (user_id,),
        )
        trade_id = conn.execute("SELECT id FROM trades ORDER BY id DESC LIMIT 1").fetchone()[0]

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO trades (tenant_id, user_id, symbol, direction, status) VALUES (1, ?, 'MSFT', 'BAD', 'open')",
                (user_id,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO trade_fills (
                    trade_id, tenant_id, fill_datetime, side, quantity, price, commission, source
                ) VALUES (?, 1, CURRENT_TIMESTAMP, 'BID', 1, 100, 0, 'manual')
                """,
                (trade_id,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO trade_fills (
                    trade_id, tenant_id, fill_datetime, side, quantity, price, commission, source
                ) VALUES (?, 1, CURRENT_TIMESTAMP, 'BUY', -1, 100, 0, 'manual')
                """,
                (trade_id,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO trade_fills (
                    trade_id, tenant_id, fill_datetime, side, quantity, price, commission, source
                ) VALUES (?, 2, CURRENT_TIMESTAMP, 'BUY', 1, 100, 0, 'manual')
                """,
                (trade_id,),
            )
