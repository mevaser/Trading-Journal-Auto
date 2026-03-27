from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.ibkr.dto import ExecutionDTO
from app.db.models import Trade
from app.services.import_models import TradeResolutionAction, TradeResolutionResult


class TradeResolver:
    async def _find_open_trade(
        self,
        session: AsyncSession,
        tenant_id: int,
        symbol: str,
    ):
        stmt = (
            select(Trade)
            .where(
                Trade.tenant_id == tenant_id,
                Trade.symbol == symbol,
                Trade.status == "open",
            )
            .order_by(Trade.created_at.asc(), Trade.id.asc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def resolve_execution(
        self,
        execution: ExecutionDTO,
        session: AsyncSession,
        tenant_id: int,
    ) -> TradeResolutionResult:
        """Resolve an imported execution to its trade outcome."""
        trade = await self._find_open_trade(
            session=session,
            tenant_id=tenant_id,
            symbol=execution.symbol,
        )
        if trade is not None:
            return TradeResolutionResult(
                action=TradeResolutionAction.UPDATED,
                trade_id=trade.id,
                fill_id=None,
                reason="matched existing open trade by symbol",
            )

        return TradeResolutionResult(
            action=TradeResolutionAction.CREATED,
            trade_id=None,
            fill_id=None,
            reason="no matching open trade found",
        )
