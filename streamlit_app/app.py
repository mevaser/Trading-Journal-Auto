from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
TRADES_ENDPOINT = f"{API_BASE_URL}/trades/"


@st.cache_data(ttl=30)
def fetch_trades() -> pd.DataFrame:
    response = requests.get(TRADES_ENDPOINT, timeout=10)
    response.raise_for_status()
    payload = response.json()
    return pd.DataFrame(payload)


st.title("Trading Journal Dashboard")

try:
    data = fetch_trades()
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to load trades from {TRADES_ENDPOINT}: {exc}")
    st.stop()

if data.empty:
    st.info("No trades found.")
    st.stop()

for column in ["user_id", "id"]:
    if column in data.columns:
        data.drop(columns=[column], inplace=True)

preferred_columns = [
    "symbol",
    "direction",
    "quantity",
    "portfolio_pct",
    "entry_price",
    "entry_date",
    "reason_entry",
    "strategy",
    "estimates",
    "stop_loss",
    "exit_price",
    "exit_date",
    "reason_exit",
    "pnl_usd",
    "pnl_pct",
    "is_intraday",
]

existing_columns = [column for column in preferred_columns if column in data.columns]
if existing_columns:
    data = data[existing_columns]

st.subheader("Portfolio Summary")
st.write("Total Trades", len(data))
if "pnl_usd" in data.columns:
    st.write("Total PnL ($)", round(pd.to_numeric(data["pnl_usd"], errors="coerce").sum(), 2))
if "pnl_pct" in data.columns:
    st.write(
        "Average Return (%)",
        round(pd.to_numeric(data["pnl_pct"], errors="coerce").mean(), 2),
    )

with st.expander("Filters"):
    filtered = data.copy()
    if "strategy" in data.columns:
        strategy_values = sorted(data["strategy"].dropna().astype(str).unique().tolist())
        strategy_filter = st.selectbox("Strategy", options=[""] + strategy_values)
        if strategy_filter:
            filtered = filtered[filtered["strategy"].astype(str) == strategy_filter]

    if "symbol" in data.columns:
        symbol_values = sorted(data["symbol"].dropna().astype(str).unique().tolist())
        symbol_filter = st.selectbox("Symbol", options=[""] + symbol_values)
        if symbol_filter:
            filtered = filtered[filtered["symbol"].astype(str) == symbol_filter]

st.subheader("Trade List")
st.dataframe(filtered, use_container_width=True)
