from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError

from app.observability import DomainValidationError


_CONSTRAINT_RE = re.compile(r"(?:constraint failed|violates .* constraint)[: ]+([a-zA-Z0-9_\.]+)", re.IGNORECASE)


def map_fill_integrity_error(exc: IntegrityError, *, trade_id: int | None = None, fill_id: int | None = None) -> DomainValidationError:
    raw = f"{exc}\n{getattr(exc, 'orig', '')}"
    normalized = raw.lower()
    constraint = _extract_constraint_name(raw)

    details: dict[str, object] = {}
    if trade_id is not None:
        details["trade_id"] = trade_id
    if fill_id is not None:
        details["fill_id"] = fill_id
    if constraint:
        details["constraint"] = constraint

    if _matches_any(normalized, ("ck_trade_fills_quantity_positive", "quantity > 0")):
        return DomainValidationError("quantity must be greater than 0", details=details or None)
    if _matches_any(normalized, ("ck_trade_fills_price_positive", "price > 0")):
        return DomainValidationError("price must be greater than 0", details=details or None)
    if _matches_any(normalized, ("ck_trade_fills_commission_non_negative", "commission >= 0")):
        return DomainValidationError("commission must be greater than or equal to 0", details=details or None)
    if _matches_any(
        normalized,
        (
            "uq_trade_fills_tenant_source_external_fill_id",
            "unique constraint failed: trade_fills.tenant_id, trade_fills.source, trade_fills.external_fill_id",
        ),
    ):
        return DomainValidationError(
            "external_fill_id already exists for this tenant and source",
            details=details or None,
        )

    return DomainValidationError("fill violates database integrity constraints", details=details or None)


def _extract_constraint_name(raw: str) -> str | None:
    match = _CONSTRAINT_RE.search(raw)
    if not match:
        return None
    value = match.group(1).strip().strip('"').strip("'")
    if "." in value:
        value = value.split(".")[-1]
    return value or None


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in value for pattern in patterns)
