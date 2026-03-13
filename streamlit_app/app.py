import streamlit as st
import pandas as pd
import requests

# 🔄 Fetch data from FastAPI
response = requests.get("http://localhost:8000/trades/")
data = pd.DataFrame(response.json())

# ❌ Remove columns not needed
data.drop(columns=["user_id", "id"], inplace=True)

# ✅ Reorder columns for better UX
data = data[[
    "symbol", "direction", "quantity", "portfolio_pct",  # basic info
    "entry_price", "entry_date", "reason_entry", "strategy", "estimates", "stop_loss",  # entry
    "exit_price", "exit_date", "reason_exit",  # exit
    "pnl_usd", "pnl_pct", "is_intraday"  # outcome
]]

# 🧮 Portfolio Summary
st.markdown("### 📊 Portfolio Summary")
st.write("**Total Trades**", len(data))
st.write("**Total PnL ($)**", round(data["pnl_usd"].astype(float).sum(), 2))
st.write("**Average Return (%)**", round(data["pnl_pct"].astype(float).mean(), 2))

# 📑 Filter Options
with st.expander("🔍 Filters"):
    strategy_filter = st.selectbox("Strategy", options=[""] + sorted(data["strategy"].dropna().unique().tolist()))
    symbol_filter = st.selectbox("Symbol", options=[""] + sorted(data["symbol"].dropna().unique().tolist()))

    if strategy_filter:
        data = data[data["strategy"] == strategy_filter]
    if symbol_filter:
        data = data[data["symbol"] == symbol_filter]

# 📋 Display Trade Table
st.markdown("### 📑 Trade List")
st.dataframe(data, use_container_width=True)
