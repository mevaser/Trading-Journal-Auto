from __future__ import annotations

from datetime import UTC, datetime

from app.brokers.ibkr.schemas import ExecutionPreview
from app.domain.executions.exceptions import ExecutionMappingError
from app.domain.executions.models import ExecutionDTO


def map_execution_preview_to_dto(preview: ExecutionPreview) -> ExecutionDTO:
    """Map an IBKR execution preview object into the domain ExecutionDTO."""
    exec_id = _require_text(preview.exec_id, field_name="exec_id")
    symbol = _require_text(preview.symbol, field_name="symbol").upper()
    side = _normalize_side(preview.side)
    quantity = _require_positive_float(preview.shares, field_name="quantity")
    price = _require_positive_float(preview.price, field_name="price")
    account = _require_text(preview.account, field_name="account")
    execution_time = _parse_execution_time(preview.execution_time)

    return ExecutionDTO(
        exec_id=exec_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        account=account,
        execution_time=execution_time,
    )


def _normalize_side(raw_side: str | None) -> str:
    """Normalize broker-specific side values into BUY/SELL."""
    normalized = _require_text(raw_side, field_name="side").upper()
    if normalized in {"BUY", "BOT"}:
        return "BUY"
    if normalized in {"SELL", "SLD"}:
        return "SELL"
    raise ExecutionMappingError(f"Invalid side: {raw_side!r}")


def _parse_execution_time(raw_time: str | None) -> datetime:
    """Parse IBKR execution time formats and return a UTC datetime value."""
    text = _require_text(raw_time, field_name="execution_time")
    iso_candidate = text.replace("Z", "+00:00")
    try:
        parsed_iso = datetime.fromisoformat(iso_candidate)
        if parsed_iso.tzinfo is None:
            return parsed_iso.replace(tzinfo=UTC)
        return parsed_iso.astimezone(UTC)
    except ValueError:
        pass

    for fmt in ("%Y%m%d  %H:%M:%S", "%Y%m%d-%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue

    raise ExecutionMappingError(f"Invalid execution_time: {raw_time!r}")


def _require_text(value: str | None, *, field_name: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ExecutionMappingError(f"Missing required field: {field_name}")
    return text


def _require_positive_float(value: float | None, *, field_name: str) -> float:
    if value is None:
        raise ExecutionMappingError(f"Missing required field: {field_name}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ExecutionMappingError(f"Invalid numeric field: {field_name}") from exc
    if parsed <= 0:
        raise ExecutionMappingError(f"Field must be > 0: {field_name}")
    return parsed
