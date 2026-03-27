from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Final

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.ibkr.dto import ExecutionDTO
from app.db.models import BrokerExecutionFill, ImportRun, ImportRunRecord
from app.services.lifecycle_projection_service import mark_partition_dirty_for_canonical

_DECIMAL_Q8: Final[Decimal] = Decimal("0.00000001")
_TERMINAL_SUCCESS: Final[set[str]] = {
    "duplicate_skipped",
    "resolved_inserted",
    "resolved_superseded",
}


class RetryableProcessingError(RuntimeError):
    """Raised when race conditions require a full record retry."""


@dataclass(slots=True, frozen=True)
class NormalizedExecution:
    source: str
    broker_account_id: str | None
    external_execution_id: str | None
    symbol: str | None
    side: str | None
    asset_type: str | None
    quantity: Decimal | None
    price: Decimal | None
    commission: Decimal
    currency: str | None
    execution_time_utc: datetime | None


def _q8(value: Decimal) -> Decimal:
    return value.quantize(_DECIMAL_Q8, rounding=ROUND_HALF_UP)


def _fmt_q8(value: Decimal) -> str:
    return format(_q8(value), ".8f")


def _fmt_time_utc(value: datetime | None) -> str:
    if value is None:
        return ""
    utc_value = value.astimezone(UTC)
    return utc_value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def normalize_execution(
    execution: ExecutionDTO,
    *,
    source: str,
    default_broker_account_id: str | None,
) -> NormalizedExecution:
    broker_account_id = (execution.account_id or default_broker_account_id or None)
    if broker_account_id is not None:
        broker_account_id = broker_account_id.strip() or None

    external_execution_id = (execution.external_execution_id or None)
    if external_execution_id is not None:
        external_execution_id = external_execution_id.strip() or None

    symbol = (execution.symbol or None)
    if symbol is not None:
        symbol = symbol.strip().upper() or None

    currency = (execution.currency or None)
    if currency is not None:
        currency = currency.strip().upper() or None

    execution_time_utc = execution.execution_time.astimezone(UTC) if execution.execution_time else None

    quantity = _q8(execution.quantity) if execution.quantity is not None else None
    price = _q8(execution.price) if execution.price is not None else None
    commission = _q8(execution.commission if execution.commission is not None else Decimal("0"))

    return NormalizedExecution(
        source=source,
        broker_account_id=broker_account_id,
        external_execution_id=external_execution_id,
        symbol=symbol,
        side=execution.side.value if execution.side else None,
        asset_type=execution.asset_type.value if execution.asset_type else None,
        quantity=quantity,
        price=price,
        commission=commission,
        currency=currency,
        execution_time_utc=execution_time_utc,
    )


def payload_hash(normalized: NormalizedExecution, *, tenant_id: int) -> str:
    canonical_parts = [
        str(tenant_id),
        normalized.source,
        normalized.broker_account_id or "",
        normalized.external_execution_id or "",
        normalized.symbol or "",
        normalized.side or "",
        normalized.asset_type or "",
        _fmt_q8(normalized.quantity or Decimal("0")),
        _fmt_q8(normalized.price or Decimal("0")),
        _fmt_q8(normalized.commission),
        normalized.currency or "",
        _fmt_time_utc(normalized.execution_time_utc),
    ]
    canonical_text = "|".join(canonical_parts)
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()


def _raw_payload_json(normalized: NormalizedExecution, *, tenant_id: int, hash_value: str) -> str:
    payload = {
        "tenant_id": tenant_id,
        "source": normalized.source,
        "broker_account_id": normalized.broker_account_id,
        "external_execution_id": normalized.external_execution_id,
        "symbol": normalized.symbol,
        "side": normalized.side,
        "asset_type": normalized.asset_type,
        "quantity": _fmt_q8(normalized.quantity or Decimal("0")),
        "price": _fmt_q8(normalized.price or Decimal("0")),
        "commission": _fmt_q8(normalized.commission),
        "currency": normalized.currency,
        "execution_time_utc": _fmt_time_utc(normalized.execution_time_utc) or None,
        "payload_hash": hash_value,
    }
    return json.dumps(payload, sort_keys=True)


def _validate_record(record: ImportRunRecord) -> str | None:
    if not record.broker_account_id:
        return "broker_account_id is required"
    if not record.external_execution_id:
        return "external_execution_id is required"
    if not record.symbol:
        return "symbol is required"
    if record.side not in {"BUY", "SELL"}:
        return "side must be BUY or SELL"
    if not record.asset_type:
        return "asset_type is required"
    if record.quantity is None or Decimal(record.quantity) <= Decimal("0"):
        return "quantity must be > 0"
    if record.price is None or Decimal(record.price) <= Decimal("0"):
        return "price must be > 0"
    if record.commission is None or Decimal(record.commission) < Decimal("0"):
        return "commission must be >= 0"
    if record.execution_time_utc is None:
        return "execution_time_utc is required"
    return None


def _mark_terminal(
    record: ImportRunRecord,
    *,
    status: str,
    canonical_execution_fill_id: int | None,
    error_code: str | None = None,
    error_message: str | None = None,
    status_reason: str | None = None,
) -> None:
    record.status = status
    record.canonical_execution_fill_id = canonical_execution_fill_id
    record.error_code = error_code
    record.error_message = error_message
    record.status_reason = status_reason
    record.resolved_at = datetime.now(UTC)


def _canonical_from_record(record: ImportRunRecord, *, import_run_id: int) -> BrokerExecutionFill:
    # Validation guarantees required fields are present.
    if not record.payload_hash:
        raise ValueError("payload_hash is required")
    return BrokerExecutionFill(
        tenant_id=record.tenant_id,
        import_run_id=import_run_id,
        source=record.source,
        broker_account_id=record.broker_account_id,  # type: ignore[arg-type]
        external_execution_id=record.external_execution_id,  # type: ignore[arg-type]
        symbol=record.symbol,  # type: ignore[arg-type]
        side=record.side,  # type: ignore[arg-type]
        asset_type=record.asset_type,  # type: ignore[arg-type]
        quantity=record.quantity,  # type: ignore[arg-type]
        price=record.price,  # type: ignore[arg-type]
        commission=record.commission,  # type: ignore[arg-type]
        currency=record.currency,
        execution_time_utc=record.execution_time_utc,  # type: ignore[arg-type]
        payload_hash=record.payload_hash,
        raw_payload_json=record.raw_payload_json,
        is_active=True,
    )


async def stage_records(
    db: AsyncSession,
    *,
    import_run: ImportRun,
    tenant_id: int,
    source: str,
    default_broker_account_id: str | None,
    executions: list[ExecutionDTO],
) -> list[ImportRunRecord]:
    normalized = [
        normalize_execution(item, source=source, default_broker_account_id=default_broker_account_id)
        for item in executions
    ]
    normalized.sort(
        key=lambda item: (
            item.execution_time_utc or datetime.min.replace(tzinfo=UTC),
            item.external_execution_id or "",
        )
    )

    staged: list[ImportRunRecord] = []
    for seq, item in enumerate(normalized, start=1):
        hash_value = payload_hash(item, tenant_id=tenant_id)
        row = ImportRunRecord(
            import_run_id=import_run.id,
            tenant_id=tenant_id,
            record_seq=seq,
            source=source,
            broker_account_id=item.broker_account_id,
            external_execution_id=item.external_execution_id,
            symbol=item.symbol,
            side=item.side,
            asset_type=item.asset_type,
            quantity=item.quantity,
            price=item.price,
            commission=item.commission,
            currency=item.currency,
            execution_time_utc=item.execution_time_utc,
            payload_hash=hash_value,
            raw_payload_json=_raw_payload_json(item, tenant_id=tenant_id, hash_value=hash_value),
            status="staged",
        )
        db.add(row)
        staged.append(row)

    await db.flush()
    return staged


async def process_staged_record(
    db: AsyncSession,
    *,
    record: ImportRunRecord,
    import_run_id: int,
) -> str:
    if record.status != "staged":
        return record.status

    validation_error = _validate_record(record)
    if validation_error is not None:
        _mark_terminal(
            record,
            status="failed_validation",
            canonical_execution_fill_id=None,
            error_code="validation_error",
            error_message=validation_error,
        )
        return record.status

    last_error: Exception | None = None
    for _attempt in range(1, 4):
        try:
            await _process_attempt(db, record=record, import_run_id=import_run_id)
        except (RetryableProcessingError, IntegrityError) as exc:
            last_error = exc
            continue

        _enforce_success_canonical_id(record)
        return record.status

    _mark_terminal(
        record,
        status="failed_processing",
        canonical_execution_fill_id=None,
        error_code="supersede_retry_exhausted",
        error_message=str(last_error) if last_error is not None else "retry budget exhausted",
    )
    return record.status


def _enforce_success_canonical_id(record: ImportRunRecord) -> None:
    if record.status in _TERMINAL_SUCCESS and record.canonical_execution_fill_id is None:
        _mark_terminal(
            record,
            status="failed_processing",
            canonical_execution_fill_id=None,
            error_code="missing_canonical_id",
            error_message="successful terminal status without canonical_execution_fill_id",
        )


async def _process_attempt(
    db: AsyncSession,
    *,
    record: ImportRunRecord,
    import_run_id: int,
) -> None:
    inserted_row_id = await _try_insert_canonical(db, record=record, import_run_id=import_run_id)
    if inserted_row_id is not None:
        inserted_row = await db.get(BrokerExecutionFill, inserted_row_id)
        _mark_terminal(
            record,
            status="resolved_inserted",
            canonical_execution_fill_id=inserted_row_id,
        )
        if inserted_row is not None:
            await mark_partition_dirty_for_canonical(
                db,
                canonical_execution_fill=inserted_row,
            )
        return

    active = await _get_active_row_for_update(db, record=record)
    if active is None:
        raise RetryableProcessingError("active canonical row disappeared during retry")

    if active.payload_hash == record.payload_hash:
        _mark_terminal(
            record,
            status="duplicate_skipped",
            canonical_execution_fill_id=active.id,
        )
        return

    new_row = _canonical_from_record(record, import_run_id=import_run_id)
    new_row.supersedes_execution_fill = active
    active.is_active = False
    active.superseded_by_execution_fill = new_row
    db.add(new_row)

    try:
        await db.flush()
    except IntegrityError as exc:
        raise RetryableProcessingError(str(exc)) from exc

    _mark_terminal(
        record,
        status="resolved_superseded",
        canonical_execution_fill_id=new_row.id,
    )
    await mark_partition_dirty_for_canonical(
        db,
        canonical_execution_fill=new_row,
        previous_active_fill=active,
    )


async def _try_insert_canonical(
    db: AsyncSession,
    *,
    record: ImportRunRecord,
    import_run_id: int,
) -> int | None:
    candidate = _canonical_from_record(record, import_run_id=import_run_id)
    try:
        async with db.begin_nested():
            db.add(candidate)
            await db.flush()
            return candidate.id
    except IntegrityError:
        return None


async def _get_active_row_for_update(
    db: AsyncSession,
    *,
    record: ImportRunRecord,
) -> BrokerExecutionFill | None:
    stmt = (
        select(BrokerExecutionFill)
        .where(
            and_(
                BrokerExecutionFill.tenant_id == record.tenant_id,
                BrokerExecutionFill.source == record.source,
                BrokerExecutionFill.broker_account_id == record.broker_account_id,
                BrokerExecutionFill.external_execution_id == record.external_execution_id,
                BrokerExecutionFill.is_active.is_(True),
            )
        )
        .order_by(BrokerExecutionFill.id.desc())
        .limit(1)
        .with_for_update()
    )
    return (await db.execute(stmt)).scalar_one_or_none()
