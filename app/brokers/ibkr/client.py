from __future__ import annotations

from datetime import datetime, timezone
import logging
import threading
from typing import Any

from ibapi.client import EClient
from ibapi.execution import ExecutionFilter
from ibapi.wrapper import EWrapper

from app.brokers.ibkr.schemas import ExecutionPreview
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class _IBAPIClient(EWrapper, EClient):
    """Low-level IB API client that reports connection lifecycle events."""

    def __init__(self, owner: "IBKRClient") -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        self._owner = owner

    def nextValidId(self, orderId: int) -> None:  # noqa: N802 (IB API callback naming)
        """Called by IB after successful handshake."""
        self._owner._mark_connected(orderId)

    def error(self, reqId: int, errorCode: int, errorString: str, *args: Any) -> None:  # noqa: N802
        """Called by IB for warnings and errors."""
        logger.error(
            "IBKR error req_id=%s code=%s message=%s extra=%s",
            reqId,
            errorCode,
            errorString,
            args,
        )

    def connectionClosed(self) -> None:  # noqa: N802
        """Called by IB when socket connection is closed."""
        super().connectionClosed()
        self._owner._mark_disconnected()

    def execDetails(self, reqId: int, contract: Any, execution: Any) -> None:  # noqa: N802
        """Called by IB for each execution row in reqExecutions response."""
        self._owner._handle_exec_details(reqId, contract, execution)

    def execDetailsEnd(self, reqId: int) -> None:  # noqa: N802
        """Called by IB when reqExecutions response stream is complete."""
        self._owner._handle_exec_details_end(reqId)


class IBKRClient:
    """Minimal IBKR client that manages API connection lifecycle."""

    def __init__(self) -> None:
        settings = get_settings()
        self._host = settings.ibkr_host
        self._port = settings.ibkr_port
        self._client_id = settings.ibkr_client_id
        self._timeout_seconds = settings.ibkr_timeout_seconds

        self._connected = False
        self._ready_event = threading.Event()
        self._state_lock = threading.Lock()

        self._app = _IBAPIClient(owner=self)
        self._thread: threading.Thread | None = None
        self._exec_lock = threading.Lock()
        self._execution_results: dict[int, list[ExecutionPreview]] = {}
        self._execution_done_events: dict[int, threading.Event] = {}
        self._next_exec_request_id = 1

    def connect(self) -> None:
        """Connect to IB Gateway/TWS and wait for handshake completion."""
        with self._state_lock:
            if self._connected:
                return
            self._ready_event.clear()

            logger.info(
                "Starting IBKR socket connect (host=%s, port=%s, client_id=%s)",
                self._host,
                self._port,
                self._client_id,
            )
        self._app.connect(self._host, int(self._port), int(self._client_id))
        logger.info(
            "IBKR socket connect returned (is_connected=%s)",
            self._app.isConnected(),
        )
        if not self._app.isConnected():
            raise ConnectionError(
                "Failed to open IBKR socket connection "
                f"(host={self._host}, port={self._port}, client_id={self._client_id})"
            )

        logger.info("Starting IBKR background thread")
        thread = threading.Thread(target=self._app.run, name="ibkr-client", daemon=True)
        with self._state_lock:
            self._thread = thread
        thread.start()

        logger.info("Waiting for IBKR ready event (timeout_seconds=%s)", self._timeout_seconds)
        connected = self._ready_event.wait(timeout=float(self._timeout_seconds))
        logger.info("IBKR ready event wait finished (connected=%s)", connected)
        if not connected:
            self.disconnect()
            raise TimeoutError(
                "Timed out waiting for IBKR connection "
                f"(host={self._host}, port={self._port}, client_id={self._client_id})"
            )

    def disconnect(self) -> None:
        """Safely disconnect from IBKR if currently connected."""
        logger.info("Disconnecting IBKR client")
        with self._state_lock:
            should_disconnect = self._app.isConnected()
            thread = self._thread

        if should_disconnect:
            self._app.disconnect()

        if thread and thread.is_alive():
            thread.join(timeout=1.0)

        with self._state_lock:
            self._thread = None
            self._connected = False
            self._ready_event.clear()

    def is_connected(self) -> bool:
        """Return current connection state."""
        with self._state_lock:
            return self._connected

    def fetch_executions_preview(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ExecutionPreview]:
        """Fetch a minimal execution preview list for the requested window."""
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected")

        req_id = self._next_request_id()
        done_event = threading.Event()
        with self._exec_lock:
            self._execution_results[req_id] = []
            self._execution_done_events[req_id] = done_event

        exec_filter = ExecutionFilter()
        if start_time is not None:
            exec_filter.time = _format_ib_time(_to_utc(start_time))

        self._app.reqExecutions(req_id, exec_filter)
        completed = done_event.wait(timeout=float(self._timeout_seconds))

        with self._exec_lock:
            results = list(self._execution_results.pop(req_id, []))
            self._execution_done_events.pop(req_id, None)

        if not completed:
            raise TimeoutError("Timed out waiting for IBKR executions response")

        if end_time is None:
            return results

        end_time_utc = _to_utc(end_time)
        filtered: list[ExecutionPreview] = []
        for item in results:
            parsed_time = _parse_ib_execution_time(item.execution_time)
            if parsed_time is None or parsed_time <= end_time_utc:
                filtered.append(item)
        return filtered

    def _mark_connected(self, order_id: int) -> None:
        """Mark the client as connected after receiving first valid order id."""
        logger.info("IBKR connected; next_valid_id=%s", order_id)
        with self._state_lock:
            self._connected = True
            self._ready_event.set()

    def _mark_disconnected(self) -> None:
        """Mark the client as disconnected after connection close callback."""
        logger.info("IBKR connection closed")
        with self._state_lock:
            self._connected = False
            self._ready_event.clear()

    def _handle_exec_details(self, req_id: int, contract: Any, execution: Any) -> None:
        """Append one execution callback row to the pending request buffer."""
        preview = ExecutionPreview(
            exec_id=str(getattr(execution, "execId", "") or ""),
            symbol=_to_optional_str(getattr(contract, "symbol", None)),
            side=_to_optional_str(getattr(execution, "side", None)),
            shares=_to_optional_float(getattr(execution, "shares", None)),
            price=_to_optional_float(getattr(execution, "price", None)),
            account=_to_optional_str(getattr(execution, "acctNumber", None)),
            execution_time=_to_optional_str(getattr(execution, "time", None)),
        )
        with self._exec_lock:
            if req_id in self._execution_results:
                self._execution_results[req_id].append(preview)

    def _handle_exec_details_end(self, req_id: int) -> None:
        """Signal completion for a reqExecutions request id."""
        with self._exec_lock:
            done_event = self._execution_done_events.get(req_id)
        if done_event is not None:
            done_event.set()

    def _next_request_id(self) -> int:
        """Allocate a local request id for reqExecutions calls."""
        with self._exec_lock:
            request_id = self._next_exec_request_id
            self._next_exec_request_id += 1
        return request_id


def _to_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_ib_time(value: datetime) -> str:
    return value.strftime("%Y%m%d-%H:%M:%S")


def _parse_ib_execution_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y%m%d  %H:%M:%S", "%Y%m%d-%H:%M:%S"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
