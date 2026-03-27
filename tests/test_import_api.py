from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.tokens import issue_token_pair
from app.core.config import clear_settings_cache
from app.db.models import Base, Membership, Tenant, User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def api_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "import-api-secret")
    clear_settings_cache()

    db_file = tmp_path / "test_import_api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    test_session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_local() as session:
        t1 = Tenant(id=1, slug="alpha", name="Alpha", is_active=True)
        t2 = Tenant(id=2, slug="beta", name="Beta", is_active=True)
        u1 = User(id=1, username="alpha-user", email="alpha@example.com", password_hash="x")
        u2 = User(id=2, username="beta-user", email="beta@example.com", password_hash="x")
        session.add_all([t1, t2, u1, u2])
        await session.flush()
        session.add_all(
            [
                Membership(tenant_id=1, user_id=1, role="owner", is_active=True),
                Membership(tenant_id=2, user_id=2, role="owner", is_active=True),
            ]
        )
        await session.commit()

    token_1 = issue_token_pair(user_id=1, tenant_id=1, roles=["owner"], secret_key="import-api-secret")
    token_2 = issue_token_pair(user_id=2, tenant_id=2, roles=["owner"], secret_key="import-api-secret")
    headers_1 = {"Authorization": f"Bearer {token_1.access_token}", "X-Tenant-ID": "1"}
    headers_2 = {"Authorization": f"Bearer {token_2.access_token}", "X-Tenant-ID": "2"}

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, headers_1, headers_2

    app.dependency_overrides.clear()
    clear_settings_cache()
    await engine.dispose()


def _sync_import_payload() -> dict:
    return {
        "start_time": "2026-03-19T08:00:00Z",
        "end_time": "2026-03-19T22:00:00Z",
        "async_mode": False,
        "broker_account_id": "DU111",
        "executions": [
            {
                "external_execution_id": "exec-1",
                "symbol": "AAPL",
                "side": "BUY",
                "asset_type": "stock",
                "quantity": "2",
                "price": "100",
                "commission": "0.5",
                "execution_time": "2026-03-19T10:00:00Z",
            },
            {
                "external_execution_id": "exec-2",
                "symbol": "AAPL",
                "side": "SELL",
                "asset_type": "stock",
                "quantity": "1",
                "price": "110",
                "commission": "0.5",
                "execution_time": "2026-03-19T12:00:00Z",
            },
        ],
    }


@pytest.mark.anyio
async def test_import_requires_broker_account_id(api_client) -> None:
    client, headers_1, _ = api_client

    payload = _sync_import_payload()
    payload.pop("broker_account_id")

    response = await client.post("/broker/ibkr/import", json=payload, headers=headers_1)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_sync_import_and_replay_idempotency(api_client) -> None:
    client, headers_1, _ = api_client

    first = await client.post("/broker/ibkr/import", json=_sync_import_payload(), headers=headers_1)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["mode"] == "sync"
    assert first_payload["summary"]["total_received"] == 2
    assert first_payload["summary"]["imported"] == 2
    assert first_payload["summary"]["duplicates_skipped"] == 0
    run_id = first_payload["import_run_id"]

    run_resp = await client.get(f"/imports/{run_id}", headers=headers_1)
    assert run_resp.status_code == 200
    run_payload = run_resp.json()
    assert run_payload["status"] in {"completed", "failed"}
    assert run_payload["total_received"] == 2

    replay = await client.post("/broker/ibkr/import", json=_sync_import_payload(), headers=headers_1)
    assert replay.status_code == 200
    replay_payload = replay.json()
    assert replay_payload["summary"]["imported"] == 0
    assert replay_payload["summary"]["duplicates_skipped"] == 2


@pytest.mark.anyio
async def test_import_run_is_tenant_scoped(api_client) -> None:
    client, headers_1, headers_2 = api_client

    created = await client.post("/broker/ibkr/import", json=_sync_import_payload(), headers=headers_1)
    assert created.status_code == 200
    run_id = created.json()["import_run_id"]

    cross_tenant = await client.get(f"/imports/{run_id}", headers=headers_2)
    assert cross_tenant.status_code == 404
