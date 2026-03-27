from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.ibkr.dto import ExecutionDTO, ExecutionSide
from app.db.models import Trade, TradeFill
from app.observability import DomainValidationError, ResourceNotFoundError
from app.services.import_models import TradeResolutionAction, TradeResolutionResult
from app.services.trade_service import recalculate_trade


class ProjectionService:
    async def _create_trade_from_execution(
        self,
        session: AsyncSession,
        execution: ExecutionDTO,
        tenant_id: int,
        user_id: int,
    ) -> Trade:
        direction = "LONG" if execution.side == ExecutionSide.BUY else "SHORT"
        trade = Trade(
            tenant_id=tenant_id,
            user_id=user_id,
            symbol=execution.symbol,
            asset_type=execution.asset_type.value,
            direction=direction,
            status="open",
        )
        session.add(trade)
        await session.flush()
        return trade

    async def _create_trade_fill_from_execution(
        self,
        session: AsyncSession,
        trade: Trade,
        execution: ExecutionDTO,
        tenant_id: int,
        canonical_execution_fill_id: int | None = None,
    ) -> TradeFill:
        fill = TradeFill(
            trade_id=trade.id,
            tenant_id=tenant_id,
            fill_datetime=execution.execution_time,
            side=execution.side.value,
            quantity=execution.quantity,
            price=execution.price,
            commission=execution.commission if execution.commission is not None else Decimal("0"),
            source="manual",
            external_fill_id=execution.external_execution_id,
            canonical_execution_fill_id=canonical_execution_fill_id,
        )
        session.add(fill)
        await session.flush()
        return fill

    async def _project_fill_if_missing(
        self,
        session: AsyncSession,
        trade: Trade,
        execution: ExecutionDTO,
        tenant_id: int,
        canonical_execution_fill_id: int | None = None,
    ) -> bool:
        if canonical_execution_fill_id is not None:
            existing_fill = (
                await session.execute(
                    select(TradeFill).where(
                        TradeFill.tenant_id == tenant_id,
                        TradeFill.trade_id == trade.id,
                        TradeFill.canonical_execution_fill_id == canonical_execution_fill_id,
                    )
                )
            ).scalar_one_or_none()
        else:
            existing_fill = (
                await session.execute(
                    select(TradeFill).where(
                        TradeFill.tenant_id == tenant_id,
                        TradeFill.trade_id == trade.id,
                        TradeFill.external_fill_id == execution.external_execution_id,
                    )
                )
            ).scalar_one_or_none()
        if existing_fill is not None:
            return False

        await self._create_trade_fill_from_execution(
            session=session,
            trade=trade,
            execution=execution,
            tenant_id=tenant_id,
            canonical_execution_fill_id=canonical_execution_fill_id,
        )
        return True

    async def apply_resolution(
        self,
        session: AsyncSession,
        execution: ExecutionDTO,
        resolution: TradeResolutionResult,
        tenant_id: int,
        user_id: int,
        canonical_execution_fill_id: int | None = None,
    ):
        if resolution.action == TradeResolutionAction.CREATED:
            trade = await self._create_trade_from_execution(
                session=session,
                execution=execution,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            fill_created = await self._project_fill_if_missing(
                session=session,
                trade=trade,
                execution=execution,
                tenant_id=tenant_id,
                canonical_execution_fill_id=canonical_execution_fill_id,
            )
            if fill_created:
                await recalculate_trade(session, trade)

        if resolution.action == TradeResolutionAction.UPDATED:
            if resolution.trade_id is None:
                raise DomainValidationError("resolution.trade_id is required for UPDATED action")

            trade = (
                await session.execute(
                    select(Trade).where(
                        Trade.id == resolution.trade_id,
                        Trade.tenant_id == tenant_id,
                    )
                )
            ).scalar_one_or_none()
            if trade is None:
                raise ResourceNotFoundError(
                    "Trade not found",
                    details={"trade_id": resolution.trade_id},
                )

            fill_created = await self._project_fill_if_missing(
                session=session,
                trade=trade,
                execution=execution,
                tenant_id=tenant_id,
                canonical_execution_fill_id=canonical_execution_fill_id,
            )
            if fill_created:
                await recalculate_trade(session, trade)
