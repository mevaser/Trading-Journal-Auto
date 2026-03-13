from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.brokers.ibkr.dto import ExecutionDTO


class IBKRAdapter(ABC):
    """Contract for IBKR execution retrieval implementations."""

    @abstractmethod
    async def fetch_executions(
        self, start_time: datetime, end_time: datetime
    ) -> list[ExecutionDTO]:
        """Return normalized executions for the requested time window."""
        raise NotImplementedError
