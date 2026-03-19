from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
_auth_ctx: ContextVar[AuthContext | None] = ContextVar("auth_context", default=None)


@dataclass(frozen=True)
class AuthContext:
    user_id: int
    tenant_id: int
    roles: tuple[str, ...]
    session_id: str


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def clear_request_id() -> None:
    _request_id_ctx.set(None)


def set_auth_context(auth_context: AuthContext) -> None:
    _auth_ctx.set(auth_context)


def get_auth_context() -> AuthContext | None:
    return _auth_ctx.get()


def clear_auth_context() -> None:
    _auth_ctx.set(None)
