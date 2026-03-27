from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.brokers.ibkr.dto import AssetType, ExecutionDTO, ExecutionSide
from app.db.datetime_utils import normalize_datetime_to_utc


class ExecutionImportPayload(BaseModel):
    external_execution_id: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=20)
    side: Literal["BUY", "SELL"]
    asset_type: Literal["stock", "option", "future", "forex", "crypto", "other"] = "stock"
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    execution_time: datetime
    commission: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    account_id: str | None = None

    @field_validator("execution_time")
    @classmethod
    def normalize_execution_time(cls, value: datetime) -> datetime:
        return normalize_datetime_to_utc(value)

    def to_dto(self) -> ExecutionDTO:
        return ExecutionDTO(
            external_execution_id=self.external_execution_id,
            symbol=self.symbol.upper(),
            side=ExecutionSide(self.side),
            asset_type=AssetType(self.asset_type),
            quantity=self.quantity,
            price=self.price,
            execution_time=self.execution_time,
            commission=self.commission,
            currency=self.currency,
            account_id=self.account_id,
        )


class BrokerImportRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    async_mode: bool = True
    # TODO: Revisit whether account_ref should remain in the public API once the
    # IBKR fetch path can rely on broker_account_id end-to-end.
    account_ref: str | None = None
    broker_account_id: str = Field(min_length=1, max_length=120)
    executions: list[ExecutionImportPayload] | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_window(cls, value: datetime) -> datetime:
        return normalize_datetime_to_utc(value)


class ImportSummaryResponse(BaseModel):
    total_received: int
    imported: int
    duplicates_skipped: int
    failed: int
    trades_created: int
    trades_updated: int
    errors: list[str]


class BrokerImportResponse(BaseModel):
    mode: Literal["sync", "async"]
    import_run_id: int
    status: str
    job_id: str | None = None
    summary: ImportSummaryResponse | None = None


class ImportRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    user_id: int | None
    source: str
    broker_account_id: str | None
    status: str
    window_start: datetime | None
    window_end: datetime | None
    job_id: str | None
    total_received: int
    imported: int
    duplicates_skipped: int
    failed: int
    trades_created: int
    trades_updated: int
    error_count: int
    error_details: str | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def parsed_errors(self) -> list[str]:
        if not self.error_details:
            return []
        try:
            payload = json.loads(self.error_details)
        except json.JSONDecodeError:
            return [self.error_details]
        if isinstance(payload, list):
            return [str(item) for item in payload]
        return [str(payload)]


class ImportRunResponse(BaseModel):
    id: int
    tenant_id: int
    user_id: int | None
    source: str
    broker_account_id: str | None
    status: str
    window_start: datetime | None
    window_end: datetime | None
    job_id: str | None
    total_received: int
    imported: int
    duplicates_skipped: int
    failed: int
    trades_created: int
    trades_updated: int
    errors: list[str]
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ImportRunRead) -> "ImportRunResponse":
        return cls(
            id=model.id,
            tenant_id=model.tenant_id,
            user_id=model.user_id,
            source=model.source,
            broker_account_id=model.broker_account_id,
            status=model.status,
            window_start=model.window_start,
            window_end=model.window_end,
            job_id=model.job_id,
            total_received=model.total_received,
            imported=model.imported,
            duplicates_skipped=model.duplicates_skipped,
            failed=model.failed,
            trades_created=model.trades_created,
            trades_updated=model.trades_updated,
            errors=model.parsed_errors,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class JobRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    user_id: int | None
    import_run_id: int | None
    job_type: str
    provider: str
    external_job_id: str
    status: str
    payload_json: str | None
    result_json: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
