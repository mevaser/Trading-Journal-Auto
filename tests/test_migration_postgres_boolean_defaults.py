from __future__ import annotations

import re
from pathlib import Path


def test_wave1_migrations_use_postgres_safe_boolean_defaults_and_literals() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    migration_8b = (
        repo_root / "alembic" / "versions" / "8b7c6d5e4f31_add_tenant_identity_foundation.py"
    ).read_text(encoding="utf-8")
    migration_b91 = (
        repo_root / "alembic" / "versions" / "b91e4c2d7a10_backfill_legacy_data_adoption.py"
    ).read_text(encoding="utf-8")

    assert "sa.Column(\"is_active\", sa.Boolean(), nullable=False, server_default=sa.true())" in migration_8b
    assert "SELECT :id, :slug, :name, TRUE" in migration_8b
    assert "SELECT :tenant_id, u.id, 'owner', TRUE" in migration_8b
    assert "SELECT :id, :slug, :name, TRUE" in migration_b91
    assert "CASE WHEN u.id = :owner_user_id THEN 'owner' ELSE 'member' END, TRUE" in migration_b91

    assert "server_default=sa.text(\"1\")" not in migration_8b
    assert "is_active) \"\n        \"SELECT :id, :slug, :name, 1" not in migration_8b
    assert "is_active) \"\n        \"SELECT :tenant_id, u.id, 'owner', 1" not in migration_8b
    assert "is_active) \"\n        \"SELECT :id, :slug, :name, 1" not in migration_b91
    assert re.search(r"\bBOOLEAN\s+DEFAULT\s+1\b", migration_8b, flags=re.IGNORECASE) is None


def test_wave1_models_use_boolean_true_server_defaults() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    models = (repo_root / "app" / "db" / "models.py").read_text(encoding="utf-8")

    assert 'server_default=text("true")' in models
    assert 'is_active: Mapped[bool]' in models
    assert re.search(r"is_active: Mapped\[bool\].*server_default=text\(\"1\"\)", models) is None
