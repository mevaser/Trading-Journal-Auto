from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.auth.tokens import (
    AuthTokenError,
    decode_access_token,
    decode_refresh_token,
    issue_token_pair,
    refresh_token_pair,
)


SECRET = "unit-test-secret"


def test_issue_and_decode_access_token_claims() -> None:
    now = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)
    pair = issue_token_pair(
        user_id=101,
        tenant_id=7,
        roles=["owner"],
        secret_key=SECRET,
        now=now,
    )

    claims = decode_access_token(pair.access_token, secret_key=SECRET, now=now + timedelta(seconds=5))

    assert claims.sub == 101
    assert claims.tenant_id == 7
    assert claims.roles == ("owner",)
    assert claims.session_id == pair.session_id
    assert claims.token_type == "access"


def test_refresh_token_required_for_refresh_flow() -> None:
    now = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)
    pair = issue_token_pair(
        user_id=11,
        tenant_id=2,
        roles=["member"],
        secret_key=SECRET,
        now=now,
    )

    with pytest.raises(AuthTokenError, match="expected refresh token"):
        decode_refresh_token(pair.access_token, secret_key=SECRET, now=now + timedelta(seconds=1))


def test_refresh_flow_preserves_session_lineage_and_claim_scope() -> None:
    issued = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)
    pair = issue_token_pair(
        user_id=15,
        tenant_id=4,
        roles=["owner"],
        secret_key=SECRET,
        now=issued,
    )

    refreshed = refresh_token_pair(
        pair.refresh_token,
        secret_key=SECRET,
        now=issued + timedelta(minutes=5),
        rotate_refresh_token=True,
    )
    access_claims = decode_access_token(
        refreshed.access_token,
        secret_key=SECRET,
        now=issued + timedelta(minutes=5, seconds=1),
    )

    assert refreshed.session_id == pair.session_id
    assert refreshed.refresh_token != pair.refresh_token
    assert access_claims.sub == 15
    assert access_claims.tenant_id == 4
    assert access_claims.roles == ("owner",)
    assert access_claims.session_id == pair.session_id


def test_expired_refresh_token_is_rejected() -> None:
    issued = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)
    pair = issue_token_pair(
        user_id=1,
        tenant_id=1,
        roles=["owner"],
        secret_key=SECRET,
        now=issued,
        refresh_ttl_seconds=5,
    )

    with pytest.raises(AuthTokenError, match="token expired"):
        refresh_token_pair(
            pair.refresh_token,
            secret_key=SECRET,
            now=issued + timedelta(seconds=6),
        )
