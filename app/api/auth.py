from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_schemas import LoginRequest, LoginResponse
from app.auth.passwords import hash_password
from app.db.models import Membership, Tenant, User
from app.db.session import get_db
from app.observability import AuthenticationRequiredError
from app.services.auth_service import (
    AuthenticationError,
    authenticate_credentials,
    issue_token_pair,
    resolve_default_tenant_id,
    resolve_tenant_roles,
)


router = APIRouter(prefix="/auth", tags=["Auth"])


async def _ensure_bootstrap_login_user_if_enabled(db: AsyncSession, *, requested_email: str) -> None:
    enabled = os.getenv("AUTH_BRIDGE_BOOTSTRAP_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return

    bootstrap_email = os.getenv("AUTH_BRIDGE_BOOTSTRAP_EMAIL", "bridge@example.com").strip().lower()
    if requested_email.strip().lower() != bootstrap_email:
        return

    bootstrap_password = os.getenv("AUTH_BRIDGE_BOOTSTRAP_PASSWORD", "bridge-password-change-me")
    bootstrap_tenant_id = int(os.getenv("AUTH_BRIDGE_BOOTSTRAP_TENANT_ID", "1"))
    bootstrap_role = os.getenv("AUTH_BRIDGE_BOOTSTRAP_ROLE", "owner").strip() or "owner"

    tenant = await db.get(Tenant, bootstrap_tenant_id)
    if tenant is None:
        tenant = Tenant(
            id=bootstrap_tenant_id,
            slug=f"bridge-tenant-{bootstrap_tenant_id}",
            name=f"Bridge Tenant {bootstrap_tenant_id}",
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

    user = (await db.execute(select(User).where(User.email == bootstrap_email))).scalar_one_or_none()
    if user is None:
        username = os.getenv("AUTH_BRIDGE_BOOTSTRAP_USERNAME", "bridge_user").strip() or "bridge_user"
        existing = (await db.execute(select(User.id).where(User.username == username))).scalar_one_or_none()
        if existing is not None:
            username = f"{username}_{bootstrap_tenant_id}"

        user = User(
            username=username,
            email=bootstrap_email,
            password_hash=hash_password(bootstrap_password),
        )
        db.add(user)
        await db.flush()
    else:
        # Keep deterministic manual-test credentials when bootstrap mode is enabled.
        user.password_hash = hash_password(bootstrap_password)

    membership = (
        await db.execute(
            select(Membership).where(
                and_(Membership.user_id == user.id, Membership.tenant_id == bootstrap_tenant_id)
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = Membership(
            tenant_id=bootstrap_tenant_id,
            user_id=user.id,
            role=bootstrap_role,
            is_active=True,
        )
        db.add(membership)
    else:
        membership.is_active = True
        membership.role = bootstrap_role

    await db.commit()


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    await _ensure_bootstrap_login_user_if_enabled(db, requested_email=payload.email)

    try:
        user = await authenticate_credentials(db, principal=payload.email, password=payload.password)
        tenant_id = await resolve_default_tenant_id(db, user_id=user.id)
        roles = await resolve_tenant_roles(db, user_id=user.id, tenant_id=tenant_id)
    except AuthenticationError as exc:
        raise AuthenticationRequiredError("Invalid email or password") from exc

    token_pair = issue_token_pair(
        user_id=user.id,
        tenant_id=tenant_id,
        roles=roles,
    )
    expires_in = max(
        0,
        int((token_pair.access_expires_at - datetime.now(timezone.utc)).total_seconds()),
    )

    return LoginResponse(
        access_token=token_pair.access_token,
        token_type="bearer",
        expires_in=expires_in,
        tenant_id=tenant_id,
        roles=list(roles),
        session_id=token_pair.session_id,
    )
