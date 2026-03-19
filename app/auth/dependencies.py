from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import AuthTokenError, TokenClaims, decode_access_token
from app.core.config import get_settings
from app.db.models import Membership, Tenant
from app.db.session import get_db
from app.observability import (
    AuthContext,
    AuthenticationRequiredError,
    AuthorizationDeniedError,
    set_auth_context,
)


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TenantRequestContext:
    user_id: int
    tenant_id: int
    roles: tuple[str, ...]
    session_id: str


def _parse_access_token(
    credentials: HTTPAuthorizationCredentials | None,
) -> TokenClaims:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationRequiredError("Missing bearer token")

    try:
        return decode_access_token(credentials.credentials, secret_key=get_settings().app_secret_key)
    except AuthTokenError as exc:
        raise AuthenticationRequiredError("Invalid access token", details={"reason": str(exc)}) from exc


async def _require_active_membership(
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
        raise AuthorizationDeniedError(
            "Tenant membership is missing or inactive",
            details={"tenant_id": tenant_id, "user_id": user_id},
        )
    return roles


async def require_tenant_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-ID"),
) -> TenantRequestContext:
    claims = _parse_access_token(credentials)

    if x_tenant_id is not None and x_tenant_id != claims.tenant_id:
        raise AuthorizationDeniedError(
            "Tenant header does not match token tenant",
            details={"token_tenant_id": claims.tenant_id, "header_tenant_id": x_tenant_id},
        )

    membership_roles = await _require_active_membership(
        db,
        user_id=claims.sub,
        tenant_id=claims.tenant_id,
    )

    if not set(claims.roles).intersection(membership_roles):
        raise AuthorizationDeniedError(
            "Token roles are not valid for active tenant membership",
            details={"tenant_id": claims.tenant_id, "user_id": claims.sub},
        )

    ctx = TenantRequestContext(
        user_id=claims.sub,
        tenant_id=claims.tenant_id,
        roles=tuple(claims.roles),
        session_id=claims.session_id,
    )
    request.state.auth_context = ctx
    request.state.tenant_id = ctx.tenant_id

    set_auth_context(
        AuthContext(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            roles=ctx.roles,
            session_id=ctx.session_id,
        )
    )

    return ctx


def get_request_tenant_context(request: Request) -> TenantRequestContext:
    ctx = getattr(request.state, "auth_context", None)
    if ctx is None:
        raise AuthenticationRequiredError("Tenant context is not available for request")
    return ctx
