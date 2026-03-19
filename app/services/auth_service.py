from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import verify_password
from app.auth.tokens import TokenPair, refresh_token_pair
from app.auth.tokens import issue_token_pair as issue_token_pair_util
from app.core.config import get_settings
from app.db.models import Membership, Tenant, User


class AuthenticationError(ValueError):
    """Raised when credentials or auth context are invalid."""


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: int
    tenant_id: int
    roles: tuple[str, ...]
    session_id: str


async def authenticate_credentials(
    db: AsyncSession,
    *,
    principal: str,
    password: str,
) -> User:
    stmt = select(User).where(or_(User.username == principal, User.email == principal))
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise AuthenticationError("invalid credentials")

    if not verify_password(password, user.password_hash):
        raise AuthenticationError("invalid credentials")

    return user


async def resolve_tenant_roles(
    db: AsyncSession,
    *,
    user_id: int,
    tenant_id: int,
) -> tuple[str, ...]:
    stmt = (
        select(Membership.role)
        .join(Tenant, Membership.tenant_id == Tenant.id)
        .where(
            and_(
                Membership.user_id == user_id,
                Membership.tenant_id == tenant_id,
                Membership.is_active.is_(True),
                Tenant.is_active.is_(True),
            )
        )
    )
    roles = tuple(role for role in (await db.execute(stmt)).scalars().all() if role)
    if not roles:
        raise AuthenticationError("user has no active membership for tenant")
    return roles


async def resolve_default_tenant_id(
    db: AsyncSession,
    *,
    user_id: int,
) -> int:
    stmt = (
        select(Membership.tenant_id)
        .join(Tenant, Membership.tenant_id == Tenant.id)
        .where(
            and_(
                Membership.user_id == user_id,
                Membership.is_active.is_(True),
                Tenant.is_active.is_(True),
            )
        )
        .order_by(Membership.tenant_id.asc())
        .limit(1)
    )
    tenant_id = (await db.execute(stmt)).scalar_one_or_none()
    if tenant_id is None:
        raise AuthenticationError("user has no active membership for tenant")
    return int(tenant_id)


async def login_with_password(
    db: AsyncSession,
    *,
    principal: str,
    password: str,
    tenant_id: int,
    session_id: str | None = None,
    secret_key: str | None = None,
) -> tuple[AuthenticatedPrincipal, TokenPair]:
    user = await authenticate_credentials(db, principal=principal, password=password)
    roles = await resolve_tenant_roles(db, user_id=user.id, tenant_id=tenant_id)

    pair = issue_token_pair_util(
        user_id=user.id,
        tenant_id=tenant_id,
        roles=list(roles),
        session_id=session_id,
        secret_key=secret_key or get_settings().app_secret_key,
    )
    return (
        AuthenticatedPrincipal(
            user_id=user.id,
            tenant_id=tenant_id,
            roles=roles,
            session_id=pair.session_id,
        ),
        pair,
    )


def issue_token_pair(
    *,
    user_id: int,
    tenant_id: int,
    roles: list[str] | tuple[str, ...],
    session_id: str | None = None,
    secret_key: str | None = None,
) -> TokenPair:
    settings = get_settings()
    return issue_token_pair_util(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        session_id=session_id,
        secret_key=secret_key or settings.app_secret_key,
        access_ttl_seconds=settings.access_token_expire_minutes * 60,
    )


def refresh_login_tokens(
    refresh_token: str,
    *,
    secret_key: str | None = None,
    rotate_refresh_token: bool = True,
) -> TokenPair:
    settings = get_settings()
    return refresh_token_pair(
        refresh_token,
        secret_key=secret_key or settings.app_secret_key,
        rotate_refresh_token=rotate_refresh_token,
        access_ttl_seconds=settings.access_token_expire_minutes * 60,
    )
