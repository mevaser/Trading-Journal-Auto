from __future__ import annotations

from datetime import datetime

from app.brokers.ibkr.client import IBKRClient
from app.brokers.ibkr.mappers import map_execution_preview_to_dto
from app.domain.executions.models import ExecutionDTO


class IBKRService:
    """Service layer for basic IBKR connectivity checks."""

    def __init__(self) -> None:
        self._client = IBKRClient()

    def test_connection(self) -> dict[str, str]:
        """Attempt to connect to IBKR and return a simple status payload."""
        try:
            self._client.connect()
            if self._client.is_connected():
                return {"status": "connected"}
            return {"status": "failed", "details": "IBKR client did not report a connected state."}
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "details": str(exc)}
        finally:
            self._client.disconnect()

    def get_executions_preview(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ExecutionDTO]:
        """Fetch IBKR executions and map them into normalized domain DTOs."""
        try:
            self._client.connect()
            previews = self._client.fetch_executions_preview(start_time=start_time, end_time=end_time)
            return [map_execution_preview_to_dto(preview) for preview in previews]
        finally:
            self._client.disconnect()
