from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

ACCESS_TOKEN_TTL_SECONDS = 15 * 60
REFRESH_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
JWT_ALGORITHM = "HS256"


class AuthTokenError(ValueError):
    """Raised when a token cannot be decoded or validated."""


@dataclass(frozen=True)
class TokenClaims:
    sub: int
    tenant_id: int
    roles: tuple[str, ...]
    session_id: str
    iat: int
    exp: int
    token_type: Literal["access", "refresh"]
    nbf: int | None = None
    jti: str | None = None


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    session_id: str
    access_expires_at: datetime
    refresh_expires_at: datetime


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _json_dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sign(signing_input: bytes, secret_key: str) -> str:
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return _b64url_encode(signature)


def _encode_jwt(payload: dict[str, Any], secret_key: str) -> str:
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    encoded_header = _b64url_encode(_json_dumps(header))
    encoded_payload = _b64url_encode(_json_dumps(payload))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = _sign(signing_input, secret_key)
    return f"{encoded_header}.{encoded_payload}.{signature}"


def _decode_payload(token: str, secret_key: str) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".", maxsplit=2)
    except ValueError as exc:
        raise AuthTokenError("token format is invalid") from exc

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature = _sign(signing_input, secret_key)
    if not hmac.compare_digest(expected_signature, encoded_signature):
        raise AuthTokenError("token signature is invalid")

    try:
        header = json.loads(_b64url_decode(encoded_header).decode("utf-8"))
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise AuthTokenError("token payload is invalid") from exc

    if header.get("alg") != JWT_ALGORITHM:
        raise AuthTokenError("unsupported token algorithm")

    return payload


def _build_claims(payload: dict[str, Any], *, expected_type: Literal["access", "refresh"], now: datetime) -> TokenClaims:
    token_type = payload.get("token_type")
    if token_type != expected_type:
        raise AuthTokenError(f"expected {expected_type} token")

    required_fields = ("sub", "tenant_id", "roles", "session_id", "iat", "exp")
    if any(field not in payload for field in required_fields):
        raise AuthTokenError("token missing required claims")

    try:
        sub = int(payload["sub"])
        tenant_id = int(payload["tenant_id"])
        roles = tuple(str(role) for role in payload["roles"])
        session_id = str(payload["session_id"])
        iat = int(payload["iat"])
        exp = int(payload["exp"])
        nbf = int(payload["nbf"]) if payload.get("nbf") is not None else None
        jti = str(payload["jti"]) if payload.get("jti") is not None else None
    except (TypeError, ValueError) as exc:
        raise AuthTokenError("token claims have invalid types") from exc

    now_ts = int(now.timestamp())
    if nbf is not None and now_ts < nbf:
        raise AuthTokenError("token not yet valid")
    if now_ts >= exp:
        raise AuthTokenError("token expired")

    return TokenClaims(
        sub=sub,
        tenant_id=tenant_id,
        roles=roles,
        session_id=session_id,
        iat=iat,
        exp=exp,
        token_type=expected_type,
        nbf=nbf,
        jti=jti,
    )


def _base_claims(
    *,
    user_id: int,
    tenant_id: int,
    roles: list[str] | tuple[str, ...],
    session_id: str,
    issued_at: datetime,
    ttl_seconds: int,
    token_type: Literal["access", "refresh"],
) -> tuple[dict[str, Any], datetime]:
    issued_at_ts = int(issued_at.timestamp())
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": tenant_id,
        "roles": list(roles),
        "session_id": session_id,
        "iat": issued_at_ts,
        "nbf": issued_at_ts,
        "exp": int(expires_at.timestamp()),
        "token_type": token_type,
        "jti": str(uuid4()),
    }
    return payload, expires_at


def issue_token_pair(
    *,
    user_id: int,
    tenant_id: int,
    roles: list[str] | tuple[str, ...],
    secret_key: str,
    session_id: str | None = None,
    now: datetime | None = None,
    access_ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS,
    refresh_ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS,
) -> TokenPair:
    issued_at = now or datetime.now(timezone.utc)
    issued_at = issued_at.astimezone(timezone.utc)
    lineage_session_id = session_id or str(uuid4())

    access_payload, access_expires_at = _base_claims(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        session_id=lineage_session_id,
        issued_at=issued_at,
        ttl_seconds=access_ttl_seconds,
        token_type="access",
    )
    refresh_payload, refresh_expires_at = _base_claims(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        session_id=lineage_session_id,
        issued_at=issued_at,
        ttl_seconds=refresh_ttl_seconds,
        token_type="refresh",
    )

    return TokenPair(
        access_token=_encode_jwt(access_payload, secret_key),
        refresh_token=_encode_jwt(refresh_payload, secret_key),
        session_id=lineage_session_id,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
    )


def decode_access_token(token: str, *, secret_key: str, now: datetime | None = None) -> TokenClaims:
    payload = _decode_payload(token, secret_key)
    return _build_claims(
        payload,
        expected_type="access",
        now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc),
    )


def decode_refresh_token(token: str, *, secret_key: str, now: datetime | None = None) -> TokenClaims:
    payload = _decode_payload(token, secret_key)
    return _build_claims(
        payload,
        expected_type="refresh",
        now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc),
    )


def refresh_token_pair(
    refresh_token: str,
    *,
    secret_key: str,
    now: datetime | None = None,
    rotate_refresh_token: bool = True,
    access_ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS,
    refresh_ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS,
) -> TokenPair:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    refresh_claims = decode_refresh_token(refresh_token, secret_key=secret_key, now=now_utc)

    new_pair = issue_token_pair(
        user_id=refresh_claims.sub,
        tenant_id=refresh_claims.tenant_id,
        roles=list(refresh_claims.roles),
        secret_key=secret_key,
        session_id=refresh_claims.session_id,
        now=now_utc,
        access_ttl_seconds=access_ttl_seconds,
        refresh_ttl_seconds=refresh_ttl_seconds,
    )

    if not rotate_refresh_token:
        return TokenPair(
            access_token=new_pair.access_token,
            refresh_token=refresh_token,
            session_id=new_pair.session_id,
            access_expires_at=new_pair.access_expires_at,
            refresh_expires_at=new_pair.refresh_expires_at,
        )

    return new_pair
