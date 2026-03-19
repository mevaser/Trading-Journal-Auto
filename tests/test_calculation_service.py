from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.db.models import Trade, TradeFill
from app.services.calculation_service import calculate_trade_metrics


UTC = timezone.utc


def _fill(side: str, qty: str, price: str, ts: datetime, commission: str = "0") -> TradeFill:
    return TradeFill(
        trade_id=1,
        side=side,
        quantity=Decimal(qty),
        price=Decimal(price),
        fill_datetime=ts,
        commission=Decimal(commission),
        source="manual",
    )


def test_calculate_metrics_long_closed_intraday() -> None:
    trade = Trade(user_id=1, symbol="AAPL", direction="LONG")
    fills = [
        _fill("BUY", "10", "100", datetime(2026, 1, 10, 10, 0, tzinfo=UTC)),
        _fill("BUY", "10", "110", datetime(2026, 1, 10, 11, 0, tzinfo=UTC)),
        _fill("SELL", "20", "120", datetime(2026, 1, 10, 15, 0, tzinfo=UTC), commission="2"),
    ]

    metrics = calculate_trade_metrics(trade, fills)

    assert metrics.avg_entry_price == Decimal("105")
    assert metrics.avg_exit_price == Decimal("120")
    assert metrics.quantity_opened == Decimal("20")
    assert metrics.quantity_closed == Decimal("20")
    assert metrics.remaining_quantity == Decimal("0")
    assert metrics.status == "closed"
    assert metrics.pnl_usd == Decimal("298")
    assert metrics.is_intraday is True
    assert metrics.duration_days == 0


def test_calculate_metrics_long_partial_close() -> None:
    trade = Trade(user_id=1, symbol="MSFT", direction="LONG")
    fills = [
        _fill("BUY", "10", "100", datetime(2026, 1, 11, 10, 0, tzinfo=UTC)),
        _fill("SELL", "4", "110", datetime(2026, 1, 12, 10, 0, tzinfo=UTC), commission="1"),
    ]

    metrics = calculate_trade_metrics(trade, fills)

    assert metrics.status == "partial"
    assert metrics.quantity_opened == Decimal("10")
    assert metrics.quantity_closed == Decimal("4")
    assert metrics.remaining_quantity == Decimal("6")
    assert metrics.pnl_usd == Decimal("39")
    assert metrics.is_intraday is None
    assert metrics.duration_days is None


def test_calculate_metrics_long_open_with_entry_fills_only() -> None:
    trade = Trade(user_id=1, symbol="AMD", direction="LONG")
    fills = [
        _fill("BUY", "2", "99", datetime(2026, 2, 1, 10, 0, tzinfo=UTC)),
        _fill("BUY", "3", "101", datetime(2026, 2, 1, 11, 0, tzinfo=UTC)),
    ]

    metrics = calculate_trade_metrics(trade, fills)

    assert metrics.status == "open"
    assert metrics.avg_entry_price == Decimal("100.2")
    assert metrics.avg_exit_price is None
    assert metrics.quantity_opened == Decimal("5")
    assert metrics.quantity_closed == Decimal("0")
    assert metrics.remaining_quantity == Decimal("5")
    assert metrics.opened_at == datetime(2026, 2, 1, 10, 0, tzinfo=UTC)
    assert metrics.closed_at is None
    assert metrics.pnl_usd is None
    assert metrics.pnl_pct is None


def test_calculate_metrics_aggregates_weighted_avg_exit_price() -> None:
    trade = Trade(user_id=1, symbol="META", direction="LONG")
    fills = [
        _fill("BUY", "10", "100", datetime(2026, 2, 2, 10, 0, tzinfo=UTC)),
        _fill("SELL", "4", "105", datetime(2026, 2, 2, 11, 0, tzinfo=UTC)),
        _fill("SELL", "2", "120", datetime(2026, 2, 2, 12, 0, tzinfo=UTC)),
    ]

    metrics = calculate_trade_metrics(trade, fills)

    assert metrics.status == "partial"
    assert metrics.avg_exit_price == Decimal("110")
    assert metrics.quantity_opened == Decimal("10")
    assert metrics.quantity_closed == Decimal("6")
    assert metrics.remaining_quantity == Decimal("4")


def test_calculate_metrics_short_closed() -> None:
    trade = Trade(user_id=1, symbol="TSLA", direction="SHORT")
    fills = [
        _fill("SELL", "5", "50", datetime(2026, 2, 1, 10, 0, tzinfo=UTC)),
        _fill("BUY", "5", "40", datetime(2026, 2, 3, 10, 0, tzinfo=UTC)),
    ]

    metrics = calculate_trade_metrics(trade, fills)

    assert metrics.status == "closed"
    assert metrics.pnl_usd == Decimal("50")
    assert metrics.duration_days == 2


def test_calculate_metrics_invalid_close_qty() -> None:
    trade = Trade(user_id=1, symbol="NVDA", direction="LONG")
    fills = [
        _fill("BUY", "2", "100", datetime(2026, 2, 4, 10, 0, tzinfo=UTC)),
        _fill("SELL", "3", "101", datetime(2026, 2, 5, 10, 0, tzinfo=UTC)),
    ]

    with pytest.raises(ValueError, match="closing quantity exceeds currently open quantity at fill time"):
        calculate_trade_metrics(trade, fills)


def test_calculate_metrics_invalid_close_before_any_open() -> None:
    trade = Trade(user_id=1, symbol="NFLX", direction="LONG")
    fills = [
        _fill("SELL", "1", "350", datetime(2026, 2, 6, 9, 30, tzinfo=UTC)),
        _fill("BUY", "1", "345", datetime(2026, 2, 6, 10, 30, tzinfo=UTC)),
    ]

    with pytest.raises(ValueError, match="closing quantity exceeds currently open quantity at fill time"):
        calculate_trade_metrics(trade, fills)


def test_calculate_metrics_reopen_after_full_close_not_supported() -> None:
    trade = Trade(user_id=1, symbol="QQQ", direction="LONG")
    fills = [
        _fill("BUY", "2", "400", datetime(2026, 2, 7, 10, 0, tzinfo=UTC)),
        _fill("SELL", "2", "410", datetime(2026, 2, 7, 11, 0, tzinfo=UTC)),
        _fill("BUY", "1", "405", datetime(2026, 2, 7, 12, 0, tzinfo=UTC)),
    ]

    with pytest.raises(ValueError, match="reopening a fully closed trade is not supported"):
        calculate_trade_metrics(trade, fills)
