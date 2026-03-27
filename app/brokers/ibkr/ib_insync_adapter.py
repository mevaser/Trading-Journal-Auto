from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.brokers.ibkr.adapter import IBKRAdapter
from app.brokers.ibkr.dto import AssetType, ExecutionDTO, ExecutionSide


class IBInsyncIBKRAdapter(IBKRAdapter):
    """Production adapter backed by ib-insync."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 19,
        connect_timeout: int = 15,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.connect_timeout = connect_timeout

    async def fetch_executions(
        self,
        start_time: datetime,
        end_time: datetime,
        account_ref: str | None = None,
    ) -> list[ExecutionDTO]:
        try:
            from ib_insync import ExecFilter, IB, util
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("ib-insync is not available for IBKR import") from exc

        ib = IB()
        await ib.connectAsync(
            host=self.host,
            port=self.port,
            clientId=self.client_id,
            timeout=self.connect_timeout,
        )
        try:
            filter_time = start_time.astimezone(UTC).strftime("%Y%m%d-%H:%M:%S")
            executions = await ib.reqExecutionsAsync(
                ExecFilter(
                    time=filter_time,
                    acctCode=account_ref or "",
                )
            )
            normalized: list[ExecutionDTO] = []
            for row in executions:
                execution = row.execution
                contract = row.contract
                commission_report = getattr(row, "commissionReport", None)
                execution_time = util.parseIBDatetime(execution.time)
                if execution_time.tzinfo is None:
                    execution_time = execution_time.replace(tzinfo=UTC)
                execution_time = execution_time.astimezone(UTC)

                if execution_time < start_time.astimezone(UTC) or execution_time > end_time.astimezone(UTC):
                    continue

                normalized.append(
                    ExecutionDTO(
                        external_execution_id=str(execution.execId),
                        symbol=str(contract.symbol).upper(),
                        side=_map_side(str(execution.side)),
                        asset_type=_map_asset_type(getattr(contract, "secType", None)),
                        quantity=Decimal(str(execution.shares)),
                        price=Decimal(str(execution.price)),
                        execution_time=execution_time,
                        commission=_map_commission(commission_report),
                        currency=getattr(contract, "currency", None),
                        account_id=str(execution.acctNumber or account_ref or ""),
                    )
                )
            return normalized
        finally:
            ib.disconnect()


def _map_side(raw: str) -> ExecutionSide:
    normalized = raw.strip().upper()
    if normalized in {"BOT", "BUY"}:
        return ExecutionSide.BUY
    if normalized in {"SLD", "SELL"}:
        return ExecutionSide.SELL
    raise ValueError(f"Unsupported IBKR side: {raw}")


def _map_asset_type(raw: str | None) -> AssetType:
    normalized = (raw or "").strip().upper()
    if normalized in {"STK", "ETF"}:
        return AssetType.STOCK
    if normalized == "OPT":
        return AssetType.OPTION
    if normalized in {"FUT", "CONTFUT"}:
        return AssetType.FUTURE
    if normalized == "CASH":
        return AssetType.FOREX
    if normalized in {"CRYPTO", "CRYPTOCURRENCY"}:
        return AssetType.CRYPTO
    return AssetType.OTHER


def _map_commission(commission_report: object | None) -> Decimal | None:
    if commission_report is None:
        return None
    commission = getattr(commission_report, "commission", None)
    if commission is None:
        return None
    return Decimal(str(commission))
