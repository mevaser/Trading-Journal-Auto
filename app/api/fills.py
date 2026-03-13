from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schemas import FillRead, FillUpdate
from app.db.session import get_db
from app.services.trade_service import get_fill_or_404, get_trade_or_404, recalculate_trade


router = APIRouter(prefix="/fills", tags=["Fills"])


@router.patch("/{fill_id}", response_model=FillRead)
async def update_fill(fill_id: int, payload: FillUpdate, db: AsyncSession = Depends(get_db)):
    fill = await get_fill_or_404(db, fill_id)

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if field_name == "side" and value is not None:
            setattr(fill, field_name, value.upper())
        else:
            setattr(fill, field_name, value)

    trade = await get_trade_or_404(db, fill.trade_id)

    try:
        await db.flush()
        await recalculate_trade(db, trade)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.refresh(fill)
    return fill


@router.delete("/{fill_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_fill(fill_id: int, db: AsyncSession = Depends(get_db)) -> Response:
    fill = await get_fill_or_404(db, fill_id)
    trade = await get_trade_or_404(db, fill.trade_id)

    await db.delete(fill)

    try:
        await db.flush()
        await recalculate_trade(db, trade)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
