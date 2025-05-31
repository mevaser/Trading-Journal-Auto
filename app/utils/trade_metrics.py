from decimal import Decimal
from app.db.models import Trade

def calculate_trade_metrics(trade: Trade) -> None:
    """Update computed fields for a trade."""
    if trade.entry_price is None or trade.exit_price is None or trade.exit_date is None:
        return

    trade.pnl_usd = (trade.exit_price - trade.entry_price) * trade.quantity
    trade.pnl_pct = ((trade.exit_price - trade.entry_price) / trade.entry_price) * Decimal(100)
    trade.is_intraday = trade.entry_date.date() == trade.exit_date.date()
    trade.duration_days = (trade.exit_date.date() - trade.entry_date.date()).days
