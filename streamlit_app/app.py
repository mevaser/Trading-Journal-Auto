from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

import pandas as pd
import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _headers() -> dict[str, str]:
    token = st.session_state.get("access_token", "").strip()
    tenant_id = st.session_state.get("tenant_id", "").strip()
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    return headers


def _request_json(method: str, path: str, *, payload: dict | None = None) -> object:
    response = requests.request(
        method=method,
        url=f"{API_BASE_URL}{path}",
        json=payload,
        headers=_headers(),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def login(email: str, password: str) -> None:
    response = requests.post(
        f"{API_BASE_URL}/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    st.session_state.access_token = payload["access_token"]
    st.session_state.tenant_id = str(payload["tenant_id"])
    st.session_state.roles = payload.get("roles", [])


@st.cache_data(ttl=20, show_spinner=False)
def fetch_trades(token: str, tenant_id: str) -> pd.DataFrame:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    response = requests.get(f"{API_BASE_URL}/trades/", headers=headers, timeout=20)
    response.raise_for_status()
    payload = response.json()
    return pd.DataFrame(payload)


@st.cache_data(ttl=10, show_spinner=False)
def fetch_import_runs(token: str, tenant_id: str) -> list[dict]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    response = requests.get(f"{API_BASE_URL}/imports/?limit=30", headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="Trading Journal Dashboard", page_icon=":bar_chart:", layout="wide")
st.title("Trading Journal Dashboard")

with st.sidebar:
    st.subheader("Session")
    if "access_token" not in st.session_state:
        st.session_state.access_token = os.getenv("API_TOKEN", "")
    if "tenant_id" not in st.session_state:
        st.session_state.tenant_id = os.getenv("API_TENANT_ID", "")
    if "roles" not in st.session_state:
        st.session_state.roles = []

    with st.form("auth_form", clear_on_submit=False):
        email = st.text_input("Email", value=os.getenv("DASHBOARD_EMAIL", ""))
        password = st.text_input("Password", type="password", value=os.getenv("DASHBOARD_PASSWORD", ""))
        submitted = st.form_submit_button("Login")
        if submitted:
            try:
                login(email=email, password=password)
                st.success("Login succeeded")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Login failed: {exc}")

    st.text_input("Tenant ID", key="tenant_id")
    st.caption(f"Roles: {', '.join(st.session_state.roles) if st.session_state.roles else '-'}")
    if st.button("Clear Session"):
        st.session_state.access_token = ""
        st.session_state.tenant_id = ""
        st.session_state.roles = []

tab_trades, tab_imports = st.tabs(["Trades", "Import Control Center"])

with tab_trades:
    try:
        data = fetch_trades(st.session_state.access_token, st.session_state.tenant_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to load trades: {exc}")
        st.stop()

    if data.empty:
        st.info("No trades found.")
    else:
        st.metric("Total Trades", len(data))
        if "pnl_usd" in data.columns:
            st.metric("Total PnL ($)", round(pd.to_numeric(data["pnl_usd"], errors="coerce").sum(), 2))
        if "pnl_pct" in data.columns:
            st.metric(
                "Average Return (%)",
                round(pd.to_numeric(data["pnl_pct"], errors="coerce").mean(), 2),
            )
        st.dataframe(data, use_container_width=True)

with tab_imports:
    st.subheader("Trigger Import")
    with st.form("import_form"):
        default_end = datetime.now(UTC)
        default_start = default_end - timedelta(days=2)
        start_time = st.text_input("Start Time (ISO UTC)", value=default_start.isoformat())
        end_time = st.text_input("End Time (ISO UTC)", value=default_end.isoformat())
        async_mode = st.checkbox("Run in background (Celery)", value=True)
        account_ref = st.text_input("Account Ref (optional)")
        sample_executions_raw = st.text_area(
            "Inline Executions JSON (optional)",
            value="",
            help="Optional list of execution payloads for manual testing.",
        )
        submitted_import = st.form_submit_button("Run Import")
        if submitted_import:
            try:
                payload: dict[str, object] = {
                    "start_time": start_time,
                    "end_time": end_time,
                    "async_mode": async_mode,
                    "account_ref": account_ref or None,
                }
                if sample_executions_raw.strip():
                    payload["executions"] = json.loads(sample_executions_raw)
                result = _request_json("POST", "/broker/ibkr/import", payload=payload)
                st.success("Import request submitted")
                st.json(result)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Import failed: {exc}")

    st.subheader("Recent Runs")
    try:
        runs = fetch_import_runs(st.session_state.access_token, st.session_state.tenant_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to load import history: {exc}")
        st.stop()

    if not runs:
        st.info("No import runs yet.")
    else:
        runs_df = pd.DataFrame(runs)
        st.dataframe(runs_df, use_container_width=True)
        failed = [item for item in runs if item.get("status") == "failed"]
        st.subheader("Failures")
        if not failed:
            st.caption("No failed runs.")
        else:
            for item in failed:
                st.error(f"Run #{item['id']} failed")
                st.json({"errors": item.get("errors", [])})
