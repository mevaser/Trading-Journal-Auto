from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.passwords import hash_password
from app.auth.tokens import decode_access_token
from app.db.models import Base, Membership, Tenant, User
from app.services.auth_service import AuthenticationError, login_with_password, refresh_login_tokens


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def auth_db(tmp_path: Path):
    db_path = (tmp_path / "auth_service.db").resolve()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_local() as session:
        tenant1 = Tenant(id=1, slug="default", name="Default", is_active=True)
        tenant2 = Tenant(id=2, slug="desk-2", name="Desk 2", is_active=True)
        user = User(username="alice", email="alice@example.com", password_hash=hash_password("pass-1234"))

        session.add_all([tenant1, tenant2, user])
        await session.flush()

        session.add_all(
            [
                Membership(tenant_id=tenant1.id, user_id=user.id, role="owner", is_active=True),
                Membership(tenant_id=tenant2.id, user_id=user.id, role="member", is_active=True),
            ]
        )
        await session.commit()

    try:
        yield session_local
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_login_issues_tenant_scoped_claims(auth_db) -> None:
    async with auth_db() as session:
        principal, pair = await login_with_password(
            session,
            principal="alice",
            password="pass-1234",
            tenant_id=2,
            secret_key="auth-service-secret",
        )

    claims = decode_access_token(pair.access_token, secret_key="auth-service-secret")

    assert principal.roles == ("member",)
    assert principal.tenant_id == 2
    assert claims.tenant_id == 2
    assert claims.roles == ("member",)
    assert claims.session_id == principal.session_id


@pytest.mark.anyio
async def test_login_rejects_wrong_password(auth_db) -> None:
    async with auth_db() as session:
        with pytest.raises(AuthenticationError, match="invalid credentials"):
            await login_with_password(
                session,
                principal="alice",
                password="wrong",
                tenant_id=1,
                secret_key="auth-service-secret",
            )


@pytest.mark.anyio
async def test_login_requires_active_tenant_membership(auth_db) -> None:
    async with auth_db() as session:
        with pytest.raises(AuthenticationError, match="no active membership"):
            await login_with_password(
                session,
                principal="alice@example.com",
                password="pass-1234",
                tenant_id=99,
                secret_key="auth-service-secret",
            )


@pytest.mark.anyio
async def test_refresh_primitives_keep_session_lineage(auth_db) -> None:
    async with auth_db() as session:
        _, pair = await login_with_password(
            session,
            principal="alice",
            password="pass-1234",
            tenant_id=1,
            secret_key="auth-service-secret",
        )

    refreshed = refresh_login_tokens(
        pair.refresh_token,
        secret_key="auth-service-secret",
        rotate_refresh_token=True,
    )

    original_claims = decode_access_token(pair.access_token, secret_key="auth-service-secret")
    refreshed_claims = decode_access_token(refreshed.access_token, secret_key="auth-service-secret")

    assert refreshed.session_id == pair.session_id
    assert refreshed_claims.session_id == original_claims.session_id
    assert refreshed_claims.tenant_id == original_claims.tenant_id
    assert refreshed_claims.roles == original_claims.roles
