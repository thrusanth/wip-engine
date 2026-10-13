import html
import json
import os
import sqlite3
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

from services.shopfloor_catalog import catalog_by_product_name, load_master_catalog
from utils.transmit_scenario import inject_custom_payload

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
API_KEY = os.getenv("WIP_API_KEY", "dev-wip-engine-key")

# 1. Page Configuration
st.set_page_config(
    page_title="WIP Exception Engine: Inventory Reconciliation",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "active_ean" not in st.session_state:
    st.session_state.active_ean = []
if "fixture_type" not in st.session_state:
    st.session_state.fixture_type = ["SHELF"]
if "sku_alert" not in st.session_state:
    st.session_state.sku_alert = 0

st.markdown(
    """
<style>
/* Target Column 1 (All Found - Green) - ONLY innermost horizontal blocks */
div[data-testid="stHorizontalBlock"]:not(:has(div[data-testid="stHorizontalBlock"])) > div:nth-child(1) button {
    background-color: #198754 !important; border-color: #198754 !important; color: #ffffff !important;
}
div[data-testid="stHorizontalBlock"]:not(:has(div[data-testid="stHorizontalBlock"])) > div:nth-child(1) button:hover {
    background-color: #157347 !important; border-color: #146c43 !important;
}

/* Target Column 2 (Not Present - Red) - ONLY innermost horizontal blocks */
div[data-testid="stHorizontalBlock"]:not(:has(div[data-testid="stHorizontalBlock"])) > div:nth-child(2) button {
    background-color: #dc3545 !important; border-color: #dc3545 !important; color: #ffffff !important;
}
div[data-testid="stHorizontalBlock"]:not(:has(div[data-testid="stHorizontalBlock"])) > div:nth-child(2) button:hover {
    background-color: #bb2d3b !important; border-color: #b02a37 !important;
}

/* Target Column 3 (Partial - Blue) - ONLY innermost horizontal blocks */
div[data-testid="stHorizontalBlock"]:not(:has(div[data-testid="stHorizontalBlock"])) > div:nth-child(3) button {
    background-color: #0d6efd !important; border-color: #0d6efd !important; color: #ffffff !important;
}
div[data-testid="stHorizontalBlock"]:not(:has(div[data-testid="stHorizontalBlock"])) > div:nth-child(3) button:hover {
    background-color: #0b5ed7 !important; border-color: #0a58ca !important;
}

/* Shared execution + offline card pills */
.exec-pill {
    display: inline-block;
    padding: 0.18rem 0.55rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    line-height: 1.2;
    margin: 0.15rem 0.35rem 0.15rem 0;
    vertical-align: middle;
}
/* SKU + EAN identifier pills — bright success green (matches control deck) */
.exec-pill-sku,
.exec-pill-ean {
    background: rgba(32, 201, 151, 0.12) !important;
    color: #20c997 !important;
    border: 1px solid rgba(32, 201, 151, 0.55) !important;
}
.exec-pill-status-verified {
    background: rgba(25, 135, 84, 0.14);
    color: #157347;
    border: 1px solid rgba(25, 135, 84, 0.25);
}
.exec-pill-status-gap {
    background: rgba(255, 193, 7, 0.22);
    color: #946200;
    border: 1px solid rgba(255, 193, 7, 0.35);
}
.exec-pill-status-pending {
    background: rgba(13, 110, 253, 0.1);
    color: #0a58ca;
    border: 1px solid rgba(13, 110, 253, 0.2);
}
.power-cut-banner {
    border: 2px solid #dc3545;
    border-radius: 0.5rem;
    padding: 0.85rem 1rem;
    margin: 0.35rem 0 0.85rem;
    background: rgba(220, 53, 69, 0.1);
}
.power-cut-banner__title {
    color: #b02a37;
    font-size: 1.05rem;
    font-weight: 700;
    margin: 0 0 0.35rem;
}
.power-cut-banner__body {
    color: #842029;
    font-size: 0.85rem;
    line-height: 1.45;
    margin: 0;
}
.edge-metric-label {
    font-size: 0.875rem;
    color: rgba(49, 51, 63, 0.62);
    margin: 0 0 0.35rem 0;
    line-height: 1.2;
}
.edge-network-state {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-weight: 700;
    font-size: 0.95rem;
    color: #d97706;
    margin: 0;
    line-height: 1.35;
    word-break: break-word;
}
</style>
""",
    unsafe_allow_html=True,
)

# Main Title
st.title("WIP Exception Engine")
st.markdown("Enterprise Dashboard for Real-Time Execution Tracking & Anomaly Detection")

# ---------------------------------------------------------
# API Integration
# ---------------------------------------------------------
def fetch_bouncer_health():
    try:
        response = requests.get(f"{API_BASE_URL}/bouncer/health", timeout=3)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException:
        pass
    return None


def fetch_bouncer_rejections():
    try:
        response = requests.get(f"{API_BASE_URL}/bouncer/rejections", timeout=3)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException:
        pass
    return []


def fetch_bouncer_reconciliations():
    try:
        response = requests.get(f"{API_BASE_URL}/bouncer/reconciliations", timeout=3)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException:
        pass
    return []


def _bouncer_row_payload(row: dict) -> dict:
    nested = row.get("payload")
    if isinstance(nested, dict):
        return nested
    return row


def _bouncer_reconciliation_row_html(row: dict) -> str:
    """Single table row — ported from api_bouncer/main.py get_dashboard()."""
    payload = _bouncer_row_payload(row)
    trace_id = html.escape(str(row.get("trace_id") or payload.get("trace_id") or ""))
    product_name = html.escape(_bouncer_product_display_name(row))
    ean = html.escape(str(row.get("ean") or payload.get("ean") or ""))
    status = str(row.get("status") or payload.get("status") or "")
    format_alert = html.escape(str(row.get("format_alert") or payload.get("format_alert") or ""))
    shop_floor_action = html.escape(
        str(row.get("shop_floor_action") or payload.get("shop_floor_action") or "")
    )

    tx_hook = payload.get("transaction_engine_hook")
    tx_data = "<span class='bouncer-empty-state'>No ledger action required (Synced)</span>"
    if isinstance(tx_hook, dict) and tx_hook:
        tx_data = (
            f"<div class='bouncer-tx-data'><strong>TxType:</strong> "
            f"{html.escape(str(tx_hook.get('transaction_type', '')))}<br>"
            f"<strong>Adj:</strong> {html.escape(str(tx_hook.get('ledger_adjustments', '')))}"
        )
        unit_price = tx_hook.get("calculated_unit_price")
        if unit_price is not None:
            try:
                price_display = html.escape(f"£{float(unit_price):.2f}")
            except (TypeError, ValueError):
                price_display = html.escape(str(unit_price))
            rule = html.escape(str(tx_hook.get("compliance_rule_applied") or ""))
            tx_data += (
                f"<br><strong>Unit Price:</strong> {price_display}"
                f"<br><strong>Rule & Math:</strong> {rule}"
            )
        tx_data += "</div>"

    label_data = ""
    label_task = payload.get("label_print_task")
    if isinstance(label_task, dict) and label_task:
        encoded_sku = html.escape(str(label_task.get("encoded_sku", "")))
        instruction = html.escape(str(label_task.get("price_override_instruction", "")))
        label_data = (
            f"<div class='bouncer-label-data'>🖨️ <strong>PDA Print Task:</strong> "
            f"{encoded_sku} ({instruction})</div>"
        )

    status_class = "violation" if "VIOLATION" in status else "synced"
    status_icon = "⚠️" if "VIOLATION" in status else "✅"
    status_esc = html.escape(status)

    return (
        "<tr>"
        "<td>"
        f'<span class="bouncer-trace-id">{trace_id}</span><br>'
        f'<span class="bouncer-sku-label">{product_name}</span><br>'
        f'<span class="bouncer-ean-pill">EAN {ean}</span>'
        "</td>"
        f'<td><span class="bouncer-badge {status_class}">{status_icon} {status_esc}</span></td>'
        f'<td><span class="bouncer-alert-text">{format_alert}</span></td>'
        f'<td><span class="bouncer-action-text">{shop_floor_action}</span></td>'
        f"<td>{tx_data}{label_data}</td>"
        "</tr>"
    )


def build_bouncer_reconciliation_html(reconciliations: list[dict]) -> str:
    """One cohesive HTML document (style + thead + tbody) for iframe embedding."""
    rows_html = "".join(_bouncer_reconciliation_row_html(row) for row in reconciliations)
    return (
        "<!DOCTYPE html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "<title>Live Reconciliation Dashboard</title>"
        "<style>"
        ":root {"
        " --bouncer-bg: #0e1117; --bouncer-surface: #0e1117; --bouncer-text: #fafafa;"
        " --bouncer-text-muted: #e0e0e0; --bouncer-border: rgba(255, 255, 255, 0.1);"
        " --bouncer-brand: #fafafa; }"
        "html, body { margin: 0; padding: 0; background: transparent;"
        " font-family: system-ui, -apple-system, sans-serif; color: var(--bouncer-text); line-height: 1.5; }"
        ".bouncer-recon-root { padding: 8px 4px 16px; max-width: 100%; box-sizing: border-box;"
        " background: var(--bouncer-bg); }"
        ".bouncer-recon-title { color: var(--bouncer-brand); margin: 0 0 16px; font-size: 1.25rem;"
        " letter-spacing: -0.02em; font-weight: 600; }"
        ".bouncer-table-wrapper { background: var(--bouncer-surface); border-radius: 10px;"
        " box-shadow: none; overflow-x: auto; border: 1px solid var(--bouncer-border); }"
        "table { width: 100%; border-collapse: collapse; min-width: 900px; background: var(--bouncer-surface); }"
        "th, td { padding: 16px 20px; text-align: left; border-bottom: 1px solid #333333;"
        " vertical-align: middle; color: var(--bouncer-text-muted); }"
        "th { background: #0e1117; font-weight: 600; color: #fafafa; text-transform: uppercase;"
        " font-size: 0.75rem; letter-spacing: 0.05em; border-bottom: 1px solid rgba(255, 255, 255, 0.12); }"
        "td { background: #0e1117; }"
        ".bouncer-sku-label { font-weight: 700; color: #fafafa; }"
        ".bouncer-trace-id { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;"
        " font-size: 0.7rem; color: #a3a8b8; letter-spacing: 0.05em; }"
        ".bouncer-ean-pill { display: inline-block; margin-top: 6px; padding: 0.2rem 0.6rem;"
        " border-radius: 999px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;"
        " font-size: 0.72rem; font-weight: 700; letter-spacing: 0.02em; color: #34d399;"
        " background: rgba(16, 185, 129, 0.18); border: 1px solid rgba(52, 211, 153, 0.65); }"
        ".bouncer-badge { padding: 6px 12px; border-radius: 6px; font-weight: 600; font-size: 0.75rem;"
        " display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;"
        " font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; letter-spacing: -0.02em; }"
        ".bouncer-badge.violation { background: rgba(185, 28, 28, 0.22); color: #fecaca; border: 1px solid #f87171;"
        " box-shadow: 0 0 0 1px rgba(250, 204, 21, 0.35), 0 1px 3px rgba(0, 0, 0, 0.45); }"
        ".bouncer-badge.synced { background: rgba(21, 128, 61, 0.28); color: #bbf7d0; border: 1px solid #4ade80;"
        " box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35); }"
        ".bouncer-alert-text { font-weight: 500; color: #fafafa; font-size: 0.95rem; line-height: 1.4; display: block; }"
        ".bouncer-action-text { color: #e0e0e0; font-size: 0.9rem; }"
        ".bouncer-tx-data { background: #3d2a14; border-left: 3px solid #d97706; padding: 8px 12px;"
        " font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.75rem;"
        " color: #fde68a; border-radius: 0 6px 6px 0; line-height: 1.4; margin-bottom: 4px; }"
        ".bouncer-tx-data strong { color: #fef3c7; }"
        ".bouncer-label-data { background: #1e293b; border-left: 3px solid #64748b; padding: 6px 12px;"
        " font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.75rem;"
        " color: #e2e8f0; border-radius: 0 6px 6px 0; }"
        ".bouncer-label-data strong { color: #f1f5f9; }"
        ".bouncer-empty-state { color: #9ca3af; font-style: italic; font-size: 0.85rem; padding: 4px; }"
        "</style>"
        "</head>"
        "<body>"
        '<div class="bouncer-recon-root">'
        '<h2 class="bouncer-recon-title">Live Reconciliation Dashboard</h2>'
        '<div class="bouncer-table-wrapper">'
        "<table>"
        "<thead><tr>"
        "<th>Audit Trace / Product &amp; EAN</th>"
        "<th>Intercept Status</th>"
        "<th>Format Alert</th>"
        "<th>Shop-Floor Action</th>"
        "<th>Transaction &amp; Label Payload</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
        "</div>"
        "</div>"
        "</body>"
        "</html>"
    )


def render_bouncer_reconciliation_dashboard(reconciliations: list[dict]) -> None:
    """Embed api_bouncer-style reconciliation UI (Streamlit strips table tags from markdown)."""
    html_content = build_bouncer_reconciliation_html(reconciliations)
    frame_height = min(1200, 200 + len(reconciliations) * 100)
    components.html(html_content, height=frame_height, scrolling=True)


def fetch_telemetry():
    """Fetches the latest state from the FastAPI backend."""
    try:
        response = requests.get(f"{API_BASE_URL}/telemetry", timeout=3)
        if response.status_code != 200:
            st.error(f"Backend returned Error {response.status_code}: {response.text}")
            st.stop()
        return response.json()
    except requests.exceptions.Timeout:
        st.warning("Backend API timed out while fetching telemetry. Please check if the server is running and responsive.")
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend API: {e}")
        st.stop()

_DASHBOARD_CONTAINERS_KEY = "dashboard_containers"
_DASHBOARD_METRICS_KEY = "dashboard_metrics"
_DASHBOARD_OFFLINE_FILLS_KEY = "dashboard_offline_fill_audit"
_DASHBOARD_INVENTORY_GAP_KEY = "dashboard_inventory_gap_audit"
_DASHBOARD_OFFLINE_GAP_EXCEPTIONS_KEY = "dashboard_offline_gap_exceptions"
_DASHBOARD_ACTIVE_EXCEPTIONS_KEY = "dashboard_active_exceptions"
_DASHBOARD_MANIFEST_AUTO_CONFIRM_KEY = "dashboard_manifest_auto_confirm_audit"
_USE_CACHED_TELEMETRY_KEY = "dashboard_use_cached_telemetry"
_DASHBOARD_ACTIVE_TAB_KEY = "dashboard_active_tab"
_EDGE_AI_TAB_LOADED_KEY = "dashboard_edge_ai_sqlite_loaded"
_BOUNCER_TAB_LOADED_KEY = "dashboard_bouncer_api_loaded"

TAB_SYSTEM_OVERVIEW = "System Overview"
TAB_TELEMETRY = "Telemetry & Exceptions"
TAB_OFFLINE_FILL = "Offline Fill"
TAB_EDGE_AI = "Edge AI Autonomy"
TAB_API_BOUNCER = "API Bouncer"
TAB_SHOPFLOOR_SCENARIOS = "Shopfloor Scenarios"
DASHBOARD_TABS = [
    TAB_SYSTEM_OVERVIEW,
    TAB_TELEMETRY,
    TAB_OFFLINE_FILL,
    TAB_EDGE_AI,
    TAB_API_BOUNCER,
    TAB_SHOPFLOOR_SCENARIOS,
]

_MASTER_CATALOG = load_master_catalog()
_CATALOG_BY_NAME = catalog_by_product_name()
_SHELF_PRODUCT_NAMES = [
    row["product_name"] for row in _MASTER_CATALOG if row["fixture_type"] == "SHELF"
]
_ALL_PRODUCT_NAMES = [row["product_name"] for row in _MASTER_CATALOG]
_CATALOG_BY_EAN = {row["ean"]: row["product_name"] for row in _MASTER_CATALOG}


def _bouncer_product_display_name(row: dict) -> str:
    """Human-readable product title for the reconciliation log (master catalog fallback)."""
    payload = _bouncer_row_payload(row)
    explicit = payload.get("product_name") or row.get("product_name")
    if explicit:
        return str(explicit).strip()
    ean = str(row.get("ean") or payload.get("ean") or "").strip()
    if ean and ean in _CATALOG_BY_EAN:
        return _CATALOG_BY_EAN[ean]
    parent_sku = str(row.get("sku") or payload.get("sku") or "").strip()
    if parent_sku.startswith("EAN-") and len(parent_sku) > 4:
        catalog_name = _CATALOG_BY_EAN.get(parent_sku[4:])
        if catalog_name:
            return catalog_name
    return parent_sku or "Unknown product"


def _shelf_sku_max_capacity(product_name: str) -> int:
    """Inner pack size for shelf damage UI (falls back to BOM/case units)."""
    row = _CATALOG_BY_NAME[product_name]
    inner = row.get("inner_pack_units")
    if inner is not None:
        return int(inner)
    return int(row["bom_units"])


def _sync_scenario_a_on_sku_change() -> None:
    product_name = st.session_state.get("shopfloor_a_sku") or _SHELF_PRODUCT_NAMES[0]
    max_capacity = _shelf_sku_max_capacity(product_name)
    st.session_state.scenario_a_max_capacity = max_capacity
    st.session_state.filled_qty = max_capacity
    st.session_state.damaged_qty = 0


def _scenario_a_update_fill() -> None:
    max_capacity = int(st.session_state.scenario_a_max_capacity)
    st.session_state.damaged_qty = max_capacity - int(st.session_state.filled_qty)


def _scenario_a_update_damage() -> None:
    max_capacity = int(st.session_state.scenario_a_max_capacity)
    st.session_state.filled_qty = max_capacity - int(st.session_state.damaged_qty)


TOTAL_POWER_CUT_STATUS = "Mandatory Full Gap Scan Required"

OFFLINE_FILL_AUDIT_SKU = "PASTA-CASE-12"
OFFLINE_FILL_AUDIT_ACTION = "fill"
OFFLINE_FILL_AUDIT_QUANTITY = 12

EDGE_CAMERA_NETWORK_STATE = "[STATE: DISCONNECTED_AUTONOMY]"
# Must match artifact paths written by ft-05.py (repo root, not env overrides).
_REPO_ROOT = Path(__file__).resolve().parent
EDGE_AI_WEIGHTS_PATH = _REPO_ROOT / "local_sku_weights_ft05.json"
EDGE_AI_BUFFER_PATH = _REPO_ROOT / "offline_detection_buffer_ft05.db"


def _is_total_power_cut_exception(exc: dict) -> bool:
    if exc.get("status") == TOTAL_POWER_CUT_STATUS:
        return True
    return exc.get("kind") == "total_power_cut"


def _power_cut_quarantine(active_exceptions: list[dict]) -> tuple[set[str], set[str]]:
    """Container IDs and SKUs tied to total power-cut disaster recovery (Tab 3 only)."""
    blocked_container_ids: set[str] = set()
    blocked_skus: set[str] = set()
    for exc in active_exceptions:
        if not _is_total_power_cut_exception(exc):
            continue
        container_id = exc.get("container_id")
        sku = exc.get("sku")
        if container_id:
            blocked_container_ids.add(container_id)
        if sku:
            blocked_skus.add(sku)
    return blocked_container_ids, blocked_skus


def filter_containers_for_live_tabs(
    containers: dict,
    active_exceptions: list[dict],
) -> dict:
    """Remove disaster-recovery manifests from live shop-floor views (Tabs 1 & 2)."""
    blocked_container_ids, blocked_skus = _power_cut_quarantine(active_exceptions)
    filtered: dict = {}
    for container_id, container in containers.items():
        if container_id in blocked_container_ids:
            continue
        skus = [
            sku
            for sku in container.get("skus", [])
            if sku.get("sku") not in blocked_skus
        ]
        if not skus:
            continue
        filtered[container_id] = {**container, "skus": skus}
    return filtered


def derive_live_overview_metrics(containers: dict, base_metrics: dict) -> dict:
    """Recompute drift/task metrics from quarantined live containers only."""
    total_drift = 0
    total_shrink_cost = 0.0
    pending_edge_tasks = 0

    for container in containers.values():
        container_pending = False
        for sku in container.get("skus", []):
            drift = int(sku.get("drift", 0))
            total_drift += drift
            unit_price = float(sku.get("price") or 0.0)
            total_shrink_cost += drift * unit_price
            if int(sku.get("variance", 0)) > 0 and not sku.get("is_resolved"):
                container_pending = True
        if container_pending:
            pending_edge_tasks += 1

    return {
        **base_metrics,
        "active_flattops": len(containers),
        "detected_phantom_drift": total_drift,
        "daily_shrink_cost": total_shrink_cost,
        "pending_edge_tasks": pending_edge_tasks,
    }


def _is_offline_gap_exception(exc: dict) -> bool:
    if exc.get("status") == "Gap Scan Recommended":
        return True
    message = (exc.get("message") or "").lower()
    return "gap scan recommended" in message


def _extract_offline_recovery_payload(payload: dict) -> tuple[list, list, list]:
    """Offline recovery data only — kept separate from live flattop telemetry."""
    offline_fill_audit = payload.get("offline_fill_audit", [])
    inventory_gap_audit = payload.get("inventory_gap_audit", [])
    offline_gap_exceptions = [
        exc
        for exc in payload.get("active_exceptions", [])
        if _is_offline_gap_exception(exc)
    ]
    return offline_fill_audit, inventory_gap_audit, offline_gap_exceptions


def _persist_dashboard_telemetry(payload: dict) -> None:
    """Store latest telemetry in session so cards re-render with updated metrics."""
    st.session_state[_DASHBOARD_CONTAINERS_KEY] = payload.get("containers", {})
    st.session_state[_DASHBOARD_METRICS_KEY] = payload.get("metrics", {})
    offline_fills, gap_audit, gap_exceptions = _extract_offline_recovery_payload(payload)
    st.session_state[_DASHBOARD_OFFLINE_FILLS_KEY] = offline_fills
    st.session_state[_DASHBOARD_INVENTORY_GAP_KEY] = gap_audit
    st.session_state[_DASHBOARD_OFFLINE_GAP_EXCEPTIONS_KEY] = gap_exceptions
    st.session_state[_DASHBOARD_ACTIVE_EXCEPTIONS_KEY] = payload.get("active_exceptions", [])
    st.session_state[_DASHBOARD_MANIFEST_AUTO_CONFIRM_KEY] = payload.get(
        "manifest_auto_confirm_audit", []
    )
    st.session_state[_USE_CACHED_TELEMETRY_KEY] = True


def _load_dashboard_telemetry_from_session() -> tuple[dict | None, dict | None]:
    if not st.session_state.get(_USE_CACHED_TELEMETRY_KEY):
        return None, None
    st.session_state[_USE_CACHED_TELEMETRY_KEY] = False
    return (
        st.session_state.get(_DASHBOARD_CONTAINERS_KEY),
        st.session_state.get(_DASHBOARD_METRICS_KEY),
    )


def submit_resolution(
    container_id,
    sku,
    resolution_type,
    recovered_units=0,
    *,
    partial_flag_key: str | None = None,
):
    """Submits a resolution event to the FastAPI backend."""
    payload = {
        "container_id": container_id,
        "sku": sku,
        "resolution_type": resolution_type,
        "recovered_units": recovered_units
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/events/resolve",
            json=payload,
            headers={"X-API-Key": API_KEY},
            timeout=3,
        )
        if response.status_code != 200:
            st.error(f"Failed to submit resolution. Error {response.status_code}: {response.text}")
            st.stop()
        _persist_dashboard_telemetry(response.json())
        if partial_flag_key is not None:
            st.session_state[partial_flag_key] = False
        st.rerun()
    except requests.exceptions.Timeout:
        st.warning(f"Backend API timed out while submitting resolution for container {container_id}.")
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to submit resolution due to connection error: {e}")
        st.stop()

# Fetch data on load (prefer session cache immediately after control-deck actions)
try:
    cached_containers, cached_metrics = _load_dashboard_telemetry_from_session()
    if cached_containers is not None:
        containers = cached_containers
        metrics = cached_metrics or {
            "pending_delivery_cages": 0,
            "active_flattops": 0,
            "detected_phantom_drift": 0,
            "daily_shrink_cost": 0.0,
            "pending_edge_tasks": 0,
        }
        offline_fill_audit = st.session_state.get(_DASHBOARD_OFFLINE_FILLS_KEY, [])
        inventory_gap_audit = st.session_state.get(_DASHBOARD_INVENTORY_GAP_KEY, [])
        offline_gap_exceptions = st.session_state.get(_DASHBOARD_OFFLINE_GAP_EXCEPTIONS_KEY, [])
        active_exceptions = st.session_state.get(_DASHBOARD_ACTIVE_EXCEPTIONS_KEY, [])
        manifest_auto_confirm_audit = st.session_state.get(
            _DASHBOARD_MANIFEST_AUTO_CONFIRM_KEY, []
        )
    else:
        telemetry_data = fetch_telemetry()

        if telemetry_data and "metrics" in telemetry_data and "pending_delivery_cages" in telemetry_data["metrics"]:
            metrics = telemetry_data["metrics"]
            containers = telemetry_data.get("containers", {})
            active_exceptions = telemetry_data.get("active_exceptions", [])
            manifest_auto_confirm_audit = telemetry_data.get("manifest_auto_confirm_audit", [])
            offline_fill_audit, inventory_gap_audit, offline_gap_exceptions = (
                _extract_offline_recovery_payload(telemetry_data)
            )
        else:
            st.warning("Backend API connected, but returned incomplete data. Using fallback empty state.")
            metrics = {
                "pending_delivery_cages": 0,
                "active_flattops": 0,
                "detected_phantom_drift": 0,
                "daily_shrink_cost": 0.0,
                "pending_edge_tasks": 0
            }
            containers = {}
            offline_fill_audit = []
            inventory_gap_audit = []
            offline_gap_exceptions = []
            active_exceptions = []
            manifest_auto_confirm_audit = []

    st.session_state[_DASHBOARD_CONTAINERS_KEY] = containers
    st.session_state[_DASHBOARD_METRICS_KEY] = metrics
    st.session_state[_DASHBOARD_OFFLINE_FILLS_KEY] = offline_fill_audit
    st.session_state[_DASHBOARD_INVENTORY_GAP_KEY] = inventory_gap_audit
    st.session_state[_DASHBOARD_OFFLINE_GAP_EXCEPTIONS_KEY] = offline_gap_exceptions
    st.session_state[_DASHBOARD_ACTIVE_EXCEPTIONS_KEY] = active_exceptions
    st.session_state[_DASHBOARD_MANIFEST_AUTO_CONFIRM_KEY] = manifest_auto_confirm_audit
except Exception as e:
    st.error(f"API Connection Error: {e}")
    st.stop()

live_containers = filter_containers_for_live_tabs(containers, active_exceptions)
live_metrics = derive_live_overview_metrics(live_containers, metrics)

# ---------------------------------------------------------
# Top Header Section: Global Metrics
# ---------------------------------------------------------
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric(label="Pending Delivery Cages", value=live_metrics["pending_delivery_cages"], delta="Awaiting Breakdown", delta_color="off")
with col2:
    st.metric(label="Active Flattops", value=live_metrics["active_flattops"], delta="Live Manifests", delta_color="off")
with col3:
    st.metric(label="Detected Phantom Drift Units", value=live_metrics["detected_phantom_drift"], delta="Shrink Risk", delta_color="inverse")
with col4:
    st.metric(label="Daily Shrink Cost", value=f"£{live_metrics['daily_shrink_cost']:,.2f}", delta="Revenue Lost", delta_color="inverse")
with col5:
    if live_metrics["pending_edge_tasks"] > 0:
        st.metric(label="Pending Edge Tasks", value=live_metrics["pending_edge_tasks"], delta="Action Required", delta_color="inverse")
    else:
        st.metric(label="Pending Edge Tasks", value=live_metrics["pending_edge_tasks"], delta="All Tasks Cleared", delta_color="normal")

telemetry_rows = []
for container_id, container in live_containers.items():
    zone = container.get("zone", "")
    for sku in container.get("skus", []):
        drift_units = sku.get("drift", 0)
        if drift_units == 0:
            drift_units = sku.get("variance", 0)
        telemetry_rows.append(
            {
                "SKU": sku.get("sku", ""),
                "Name": sku.get("name") or sku.get("sku", ""),
                "EAN": sku.get("ean", ""),
                "Location": f"{container_id} / {zone}",
                "Drift": drift_units,
            }
        )

FLATTOP_CARD_CONTAINER_KWARGS = {"border": True, "width": "stretch"}

OFFLINE_CASE_EXPECTED_UNITS = {
    OFFLINE_FILL_AUDIT_SKU: OFFLINE_FILL_AUDIT_QUANTITY,
    "RICE-CASE-6": 6,
}


def render_execution_sku_profile(name: str, sku: str, ean: str = "") -> None:
    """SKU profile row shared by live execution cards and offline review cards."""
    ean_display = ean or "—"
    st.markdown(
        f"**SKU Profile:** {html.escape(name)}  \n"
        f'<span class="exec-pill exec-pill-sku">{html.escape(sku)}</span>'
        f'<span class="exec-pill exec-pill-ean">EAN {html.escape(ean_display)}</span>',
        unsafe_allow_html=True,
    )


def _unaccounted_variance_value(sku_data: dict) -> int:
    if sku_data.get("is_resolved"):
        return 0
    return int(sku_data.get("variance", 0))


def render_unaccounted_variance_metric(
    sku_data: dict,
    *,
    delta: str | None = None,
    delta_color: str = "normal",
) -> None:
    metric_kwargs = {"label": "Unaccounted Variance", "value": _unaccounted_variance_value(sku_data)}
    if delta is not None:
        metric_kwargs["delta"] = delta
        metric_kwargs["delta_color"] = delta_color
    st.metric(**metric_kwargs)


def _sku_widget_slug(sku: str) -> str:
    return sku.replace("-", "_").lower()


def _operational_widget_key(action: str, container_id: str, sku: str) -> str:
    return f"{action}_{container_id}_{_sku_widget_slug(sku)}".lower()


def _outstanding_units(sku_data: dict) -> int:
    return max(int(sku_data.get("drift", 0)), int(sku_data.get("variance", 0)))


def _requires_operational_control_deck(sku_data: dict) -> bool:
    if sku_data.get("is_resolved"):
        return False
    return int(sku_data.get("drift", 0)) > 0 or int(sku_data.get("variance", 0)) > 0


def _container_view_from_task(task: dict) -> dict:
    return {
        "id": task["container_id"],
        "status": task["status"],
        "zone": task["zone"],
    }


def _sku_view_from_task(task: dict) -> dict:
    container_fields = {"container_id", "status", "zone"}
    return {key: value for key, value in task.items() if key not in container_fields}


def render_operational_control_deck(container_data, sku_data) -> None:
    """Three-button control deck (All Found / Not Present / Partial) for any flattop SKU."""
    if not _requires_operational_control_deck(sku_data):
        return

    container_id = container_data["id"]
    sku = sku_data["sku"]
    units = _outstanding_units(sku_data)
    partial_flag = _operational_widget_key("show_partial", container_id, sku)

    if partial_flag not in st.session_state:
        st.session_state[partial_flag] = False

    st.markdown("<br>", unsafe_allow_html=True)
    ctrl_cols = st.columns(3)
    with ctrl_cols[0]:
        if st.button(
            f"All Found ({units})",
            key=_operational_widget_key("all_found", container_id, sku),
            use_container_width=True,
        ):
            submit_resolution(container_id, sku, "all", units, partial_flag_key=partial_flag)

    with ctrl_cols[1]:
        if st.button(
            "Not Present (0)",
            key=_operational_widget_key("not_present", container_id, sku),
            use_container_width=True,
        ):
            submit_resolution(container_id, sku, "none", 0, partial_flag_key=partial_flag)

    with ctrl_cols[2]:
        if st.button(
            f"Partial ({units})",
            key=_operational_widget_key("partial", container_id, sku),
            use_container_width=True,
        ):
            st.session_state[partial_flag] = not st.session_state[partial_flag]

    if st.session_state.get(partial_flag, False):
        st.warning("Partial recovery in progress — enter quantity recovered below.")
        partial_col1, partial_col2 = st.columns([2, 1])
        with partial_col1:
            max_partial = max(1, units - 1) if units > 1 else 1
            partial_qty = st.number_input(
                "Quantity Recovered?",
                min_value=1,
                max_value=max_partial,
                value=1,
                key=_operational_widget_key("partial_qty", container_id, sku),
            )
        with partial_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(
                "Confirm Partial",
                type="primary",
                key=_operational_widget_key("confirm_partial", container_id, sku),
            ):
                submit_resolution(
                    container_id,
                    sku,
                    "partial",
                    partial_qty,
                    partial_flag_key=partial_flag,
                )


def render_execution_telemetry_card(task: dict) -> None:
    """Strict FT-02-style template: metrics, variance alerts, and 3-column control deck."""
    container_data = _container_view_from_task(task)
    sku_data = _sku_view_from_task(task)
    product_name = sku_data.get("name", sku_data["sku"])

    with st.container(**FLATTOP_CARD_CONTAINER_KWARGS):
        st.subheader(f"Execution Telemetry: {container_data['id']}")
        st.caption(f"Last Known State: {container_data['status']} | Zone: {container_data['zone']}")
        render_execution_sku_profile(product_name, sku_data["sku"], sku_data.get("ean", ""))

        metrics_left, metrics_right = st.columns(2)
        with metrics_left:
            st.metric("Expected Quantity", sku_data["expected"])
            st.metric("Sent to Backstock", sku_data.get("backstock", 0))
        with metrics_right:
            st.metric("Worked to Shelf", sku_data["worked"])
            st.metric("Phantom Drift", sku_data["drift"])

        st.markdown("---")
        render_unaccounted_variance_metric(sku_data)

        if sku_data["is_resolved"]:
            if sku_data["resolution_type"] == "all":
                st.success("✅ **Resolved:** All units recovered and accounted for.")
            elif sku_data["resolution_type"] == "none":
                st.error("🚨 **Shrink Confirmed:** Units officially lost/unaccounted.")
            elif sku_data["resolution_type"] == "partial":
                st.warning(
                    f"⚠️ **Partial Resolution:** {sku_data['recovered_units']} found, "
                    f"{sku_data['shrink_confirmed']} confirmed as shrink."
                )
        else:
            if sku_data["drift"] > 0:
                st.warning(
                    f"⚠️ **PHANTOM DRIFT:** {sku_data['drift']} units of "
                    f"'{product_name}' are missing and completely unaccounted for in system telemetry."
                )
            elif sku_data.get("variance", 0) > 0:
                st.warning(
                    f"⚠️ **ACTION REQUIRED:** {sku_data['variance']} units unaccounted for. "
                    "System suspects untracked backstock routing."
                )
            else:
                st.success(
                    "✅ **Fully accounted:** Case split matches telemetry "
                    f"({sku_data['worked']} shelf / {sku_data.get('backstock', 0)} backstock)."
                )
            if _requires_operational_control_deck(sku_data):
                render_operational_control_deck(container_data, sku_data)


def build_tasks(containers_dict: dict) -> list[dict]:
    """One task dict per container SKU line for the strict execution telemetry template."""
    tasks: list[dict] = []
    for container_id, container in containers_dict.items():
        for sku_data in container.get("skus", []):
            tasks.append(
                {
                    "container_id": container.get("id", container_id),
                    "status": container.get("status", ""),
                    "zone": container.get("zone", ""),
                    **sku_data,
                }
            )
    return tasks


def _execution_status_pill_class(status: str) -> str:
    if status == "Verified":
        return "exec-pill-status-verified"
    if status == "Gap Scan Recommended":
        return "exec-pill-status-gap"
    if status == TOTAL_POWER_CUT_STATUS:
        return "exec-pill-status-gap"
    return "exec-pill-status-pending"


def render_execution_status_pill(status: str, label: str | None = None) -> None:
    text = html.escape(label or status)
    pill_class = _execution_status_pill_class(status)
    st.markdown(
        f'<span class="exec-pill {pill_class}">{text}</span>',
        unsafe_allow_html=True,
    )


def _offline_case_expected_units(sku: str, reconciled_units: int) -> int:
    return OFFLINE_CASE_EXPECTED_UNITS.get(sku, reconciled_units)


def _build_offline_full_sync_cards(audit_rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for row in audit_rows:
        sku = row.get("sku", "")
        action = row.get("action", "")
        key = (sku, action)
        if key not in grouped:
            grouped[key] = {
                "sku": sku,
                "name": row.get("name") or sku,
                "ean": (row.get("ean") or "").strip(),
                "action": action,
                "reconciled_units": 0,
                "sync_status": row.get("sync_status", "Synced / Offline Fill"),
                "latest_timestamp": row.get("timestamp", ""),
            }
        grouped[key]["reconciled_units"] += int(row.get("quantity", 1))
        if row.get("timestamp", "") > grouped[key]["latest_timestamp"]:
            grouped[key]["latest_timestamp"] = row.get("timestamp", "")

    cards: list[dict] = []
    for entry in grouped.values():
        sku = entry["sku"]
        reconciled = entry["reconciled_units"]
        expected = _offline_case_expected_units(sku, reconciled)
        cards.append(
            {
                "card_type": "full_sync",
                "title": f"Offline Fill Review: {sku}",
                "sku": sku,
                "name": entry["name"],
                "ean": entry.get("ean", ""),
                "status": "Verified" if reconciled >= expected else "Pending Verification",
                "expected_units": expected,
                "reconciled_units": reconciled,
                "unlogged_backstock": max(0, expected - reconciled),
                "variance_delta": reconciled - expected,
                "action_status": f"{entry['action'].title()} · {entry['sync_status']}",
                "timestamp": entry["latest_timestamp"],
                "detail": None,
            }
        )
    return cards


def _build_offline_gap_cards(
    inventory_gap_audit: list[dict],
    gap_exception_by_sku: dict[str, dict],
) -> list[dict]:
    cards: list[dict] = []
    for row in inventory_gap_audit:
        sku = row.get("sku", "")
        exc = gap_exception_by_sku.get(sku, {})
        cards.append(
            {
                "card_type": "gap_scan",
                "title": f"Partial Fill Exception: {sku}",
                "sku": sku,
                "name": row.get("name") or sku,
                "ean": exc.get("ean", ""),
                "status": row.get("status", "Gap Scan Recommended"),
                "expected_units": int(row.get("expected_units", 0)),
                "reconciled_units": int(row.get("recorded_units", 0)),
                "unlogged_backstock": int(row.get("unlogged_backstock_units", 0)),
                "variance_delta": int(row.get("variance_delta", 0)),
                "action_status": f"{row.get('action', 'fill').title()} · Gap Scan Recommended",
                "timestamp": row.get("timestamp", ""),
                "detail": exc.get("message") or row.get("status", ""),
            }
        )
    return cards


def _offline_status_pill_label(status: str) -> str:
    if status == "Verified":
        return "Verified · Full Offline Sync"
    if status == "Gap Scan Recommended":
        return "Gap Scan Recommended"
    if status == "Pending Verification":
        return "Pending Verification"
    return status


def render_offline_review_card(card: dict) -> None:
    """Offline review card — mirrors render_execution_telemetry_card structure."""
    status = card.get("status", "")
    variance_delta = int(card.get("variance_delta", 0))
    unlogged = int(card.get("unlogged_backstock", 0))
    product_name = card.get("name") or card["sku"]

    with st.container(**FLATTOP_CARD_CONTAINER_KWARGS):
        st.subheader(card["title"])
        subtitle_parts = []
        if card.get("timestamp"):
            subtitle_parts.append(f"Last ledger update: {card['timestamp']}")
        subtitle_parts.append(card.get("action_status", ""))
        st.caption(" | ".join(part for part in subtitle_parts if part))

        render_execution_sku_profile(product_name, card["sku"], card.get("ean", ""))
        render_execution_status_pill(status, _offline_status_pill_label(status))

        metrics_left, metrics_right = st.columns(2)
        with metrics_left:
            st.metric("Expected Units", card["expected_units"])
            st.metric("Unlogged Backstock", unlogged)
        with metrics_right:
            st.metric("Worked / Reconciled Units", card["reconciled_units"])
            st.metric("Variance Delta", variance_delta)

        st.markdown("---")
        st.caption(f"**Action Status:** {card.get('action_status', '—')}")

        if status == "Verified":
            st.success(
                "✅ **Verified:** Full offline case sync reconciled to the central ledger."
            )
        elif status == "Gap Scan Recommended":
            st.warning(
                f"⚠️ **GAP SCAN RECOMMENDED:** {unlogged} unit(s) of '{product_name}' "
                f"unlogged after partial offline fill (variance delta {variance_delta})."
            )
            if card.get("detail"):
                st.caption(card["detail"])
        elif status == "Pending Verification":
            st.info("ℹ️ **Pending Verification:** Awaiting full case reconciliation.")
        elif variance_delta < 0 or unlogged > 0:
            st.warning(
                f"⚠️ **ACTION REQUIRED:** {unlogged} unlogged unit(s); "
                f"variance delta {variance_delta}. Perform a backroom gap scan."
            )


def render_offline_review_card_grid(cards: list[dict], *, columns: int = 3) -> None:
    if not cards:
        return
    grid = st.columns(columns)
    for index, card in enumerate(cards):
        with grid[index % columns]:
            render_offline_review_card(card)


def _build_power_cut_cards(
    power_cut_exceptions: list[dict],
    manifest_auto_confirm_audit: list[dict],
) -> list[dict]:
    audit_by_sku = {
        row.get("sku"): row for row in manifest_auto_confirm_audit if row.get("sku")
    }
    cards: list[dict] = []
    for exc in power_cut_exceptions:
        sku = exc.get("sku", "")
        if not sku:
            continue
        audit = audit_by_sku.get(sku, {})
        expected_units = int(audit.get("expected_units") or exc.get("units") or 0)
        confirmed_units = int(audit.get("confirmed_units") or exc.get("units") or 0)
        cards.append(
            {
                "title": f"Disaster Recovery: {sku}",
                "sku": sku,
                "name": audit.get("name") or sku,
                "ean": exc.get("ean", ""),
                "expected_units": expected_units,
                "reconciled_units": confirmed_units,
                "unlogged_backstock": expected_units,
                "variance_delta": 0,
                "action_status": "Emergency Auto-Confirm / Total Power Cut",
                "timestamp": audit.get("timestamp", ""),
                "detail": exc.get("message", ""),
                "manifest_id": exc.get("container_id", ""),
            }
        )
    return cards


def render_power_cut_recovery_card(card: dict) -> None:
    """Disaster recovery card — mirrors offline review card layout."""
    product_name = card.get("name") or card["sku"]

    with st.container(**FLATTOP_CARD_CONTAINER_KWARGS):
        st.subheader(card["title"])
        subtitle_parts = []
        if card.get("manifest_id"):
            subtitle_parts.append(f"Manifest: {card['manifest_id']}")
        if card.get("timestamp"):
            subtitle_parts.append(f"Auto-confirmed: {card['timestamp']}")
        if subtitle_parts:
            st.caption(" | ".join(subtitle_parts))

        render_execution_sku_profile(product_name, card["sku"], card.get("ean", ""))
        render_execution_status_pill(
            TOTAL_POWER_CUT_STATUS,
            TOTAL_POWER_CUT_STATUS,
        )

        metrics_left, metrics_right = st.columns(2)
        with metrics_left:
            st.metric("Expected Units", card["expected_units"])
            st.metric("Unlogged Backstock", card["unlogged_backstock"])
        with metrics_right:
            st.metric("Auto-Confirmed Units", card["reconciled_units"])
            st.metric("Variance Delta", card["variance_delta"])

        st.markdown("---")
        st.caption(f"**Action Status:** {card.get('action_status', '—')}")
        st.error("🚨 **Emergency Auto-Confirm: Mandatory Gap Scan Required**")
        if card.get("detail"):
            st.caption(card["detail"])


def render_power_cut_recovery_card_grid(cards: list[dict], *, columns: int = 3) -> None:
    if not cards:
        return
    grid = st.columns(columns)
    for index, card in enumerate(cards):
        with grid[index % columns]:
            render_power_cut_recovery_card(card)


def _truncate_feature_hash(feature_hash: str, preview_len: int = 12) -> str:
    if len(feature_hash) <= preview_len:
        return feature_hash
    return f"{feature_hash[:preview_len]}..."


@st.cache_data(show_spinner=False, ttl=30)
def _load_edge_visual_signature_rows(weights_path: str | Path) -> list[dict]:
    """Load itemized visual signature rows from the localized edge JSON cache."""
    path = Path(weights_path)
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return []

    by_hash = payload.get("by_feature_hash", {})
    if not isinstance(by_hash, dict):
        return []

    rows: list[dict] = []
    for entry in by_hash.values():
        if not isinstance(entry, dict):
            continue
        sku_id = str(entry.get("sku_id", ""))
        ean = str(entry.get("ean", "")).strip()
        feature_hash = str(entry.get("feature_hash", ""))
        rows.append(
            {
                "sku_id": sku_id,
                "ean": ean,
                "feature_hash": _truncate_feature_hash(feature_hash),
            }
        )
    return sorted(rows, key=lambda row: row.get("sku_id", ""))


def _count_cached_visual_signatures(weights_path: str | Path) -> int:
    return len(_load_edge_visual_signature_rows(weights_path))


@st.cache_data(show_spinner=False, ttl=30)
def _load_offline_detection_log_rows(db_path: str | Path) -> list[dict]:
    """Load append-only offline detection rows from the WAL buffer database."""
    db_path = str(Path(db_path))
    if not os.path.isfile(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                """
                SELECT timestamp, sku_id, detected_quantity, status
                FROM offline_detection_log
                ORDER BY id ASC;
                """
            )
            return [
                {
                    "timestamp": row[0],
                    "sku_id": row[1],
                    "detected_quantity": row[2],
                    "status": row[3],
                }
                for row in cursor.fetchall()
            ]
        except sqlite3.Error:
            return []
        finally:
            conn.close()
    except OSError:
        return []


def _count_pending_offline_scans(db_path: str | Path) -> int:
    return len(_load_offline_detection_log_rows(db_path))


if _DASHBOARD_ACTIVE_TAB_KEY not in st.session_state:
    st.session_state[_DASHBOARD_ACTIVE_TAB_KEY] = TAB_SYSTEM_OVERVIEW

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(DASHBOARD_TABS)

with tab1:
    st.session_state[_DASHBOARD_ACTIVE_TAB_KEY] = TAB_SYSTEM_OVERVIEW
    st.markdown(
        "High-level operational charts and trend summaries will appear here. "
        "Use the flattop execution cards below for live reconciliation workflows."
    )

with tab2:
    st.session_state[_DASHBOARD_ACTIVE_TAB_KEY] = TAB_TELEMETRY
    st.subheader("Live Execution Telemetry")
    telemetry_df = pd.DataFrame(telemetry_rows)
    telemetry_df = telemetry_df[telemetry_df["Drift"] != 0].sort_values(
        "Drift", ascending=False
    )
    st.dataframe(telemetry_df, use_container_width=True, hide_index=True)

with tab3:
    st.session_state[_DASHBOARD_ACTIVE_TAB_KEY] = TAB_OFFLINE_FILL
    power_cut_exceptions = [
        exc for exc in active_exceptions if _is_total_power_cut_exception(exc)
    ]
    if power_cut_exceptions:
        st.markdown(
            """
<div class="power-cut-banner">
  <p class="power-cut-banner__title">CRITICAL: Total Power Cut Detected</p>
  <p class="power-cut-banner__body">
    Delivery manifest was auto-confirmed without physical verification during a catastrophic power loss.
    A mandatory full store true-up gap scan is required before normal operations resume.
  </p>
</div>
""",
            unsafe_allow_html=True,
        )
        power_cut_cards = _build_power_cut_cards(
            power_cut_exceptions, manifest_auto_confirm_audit
        )
        render_power_cut_recovery_card_grid(power_cut_cards, columns=3)
        st.divider()

    st.caption(
        "Post-blackout recovery review — offline fills, disaster recovery, and gap exceptions. "
        "Live telemetry stays on **Telemetry & Exceptions**."
    )

    gap_exception_by_sku = {
        exc.get("sku"): exc for exc in offline_gap_exceptions if exc.get("sku")
    }

    show_all_offline_fills = st.checkbox(
        "Show all synced offline fill SKUs (disable to focus pasta case scenario)",
        value=False,
        key="offline_fill_show_all",
    )

    if show_all_offline_fills:
        audit_rows = list(offline_fill_audit)
    else:
        audit_rows = [
            row
            for row in offline_fill_audit
            if row.get("sku") == OFFLINE_FILL_AUDIT_SKU
            and row.get("action") == OFFLINE_FILL_AUDIT_ACTION
        ]

    full_sync_cards = _build_offline_full_sync_cards(audit_rows)
    gap_cards = _build_offline_gap_cards(inventory_gap_audit, gap_exception_by_sku)

    if not full_sync_cards and not gap_cards and not power_cut_exceptions:
        st.markdown("#### Awaiting offline fill data")
        st.caption(
            "Run `python3 ft-03.py` for offline fill audit cards, or `python3 ft-04.py` "
            "for total power cut disaster recovery."
        )
    else:
        summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
        with summary_col1:
            st.metric("Full Sync", len(full_sync_cards), label_visibility="visible")
        with summary_col2:
            st.metric(
                "Reconciled Units",
                sum(card["reconciled_units"] for card in full_sync_cards),
            )
        with summary_col3:
            st.metric("Gap Cases", len(gap_cards))
        with summary_col4:
            st.metric(
                "Unlogged",
                sum(card["unlogged_backstock"] for card in gap_cards),
            )

        if full_sync_cards:
            st.subheader("Post-Blackout Offline Fill Audit")
            st.caption("Full edge-buffer replays reconciled to the central ledger.")
            render_offline_review_card_grid(full_sync_cards, columns=3)

        if gap_cards:
            st.subheader("Offline Partial Fill & Gap Scan Exceptions")
            st.caption(
                "Partial fills with unlogged backstock "
                "(e.g. RICE-CASE-6: 6 expected · 4 recorded · −2 delta)."
            )
            render_offline_review_card_grid(gap_cards, columns=3)

        with st.expander("Raw ledger rows (audit trail)"):
            if audit_rows:
                st.markdown("**Synced offline fill events**")
                st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)
            if inventory_gap_audit:
                st.markdown("**Inventory gap ledger**")
                st.dataframe(
                    pd.DataFrame(inventory_gap_audit),
                    use_container_width=True,
                    hide_index=True,
                )

with tab4:
    st.session_state[_DASHBOARD_ACTIVE_TAB_KEY] = TAB_EDGE_AI
    st.subheader("Localized Edge Autonomy (Computer Vision)")
    edge_col1, edge_col2, edge_col3 = st.columns(3)
    with edge_col1:
        st.markdown(
            f'<p class="edge-metric-label">Camera Network State</p>'
            f'<p class="edge-network-state">{html.escape(EDGE_CAMERA_NETWORK_STATE)}</p>',
            unsafe_allow_html=True,
        )

    if st.button("Load edge SQLite buffers", key="load_edge_ai_sqlite"):
        st.session_state[_EDGE_AI_TAB_LOADED_KEY] = True
        _load_edge_visual_signature_rows.clear()
        _load_offline_detection_log_rows.clear()
        st.rerun()

    if st.session_state.get(_EDGE_AI_TAB_LOADED_KEY, False):
        weights_file_exists = EDGE_AI_WEIGHTS_PATH.is_file()
        buffer_file_exists = EDGE_AI_BUFFER_PATH.is_file()
        cached_signatures = _count_cached_visual_signatures(EDGE_AI_WEIGHTS_PATH)
        pending_offline_scans = _count_pending_offline_scans(EDGE_AI_BUFFER_PATH)
        with edge_col2:
            st.metric("Cached Visual Signatures", cached_signatures)
        with edge_col3:
            st.metric("Pending Offline Scans", pending_offline_scans)

        st.divider()
        signature_rows = _load_edge_visual_signature_rows(str(EDGE_AI_WEIGHTS_PATH))
        st.markdown("#### Cached Visual Signatures")
        st.caption(f"Source: `{EDGE_AI_WEIGHTS_PATH.name}`")
        if not signature_rows:
            if not weights_file_exists:
                st.info(
                    "No edge signatures cached yet — `local_sku_weights_ft05.json` was not found. "
                    "Run `python3 ft-05.py` to teach the local visual cache."
                )
            else:
                st.info(
                    "No edge signatures cached yet. Run `python3 ft-05.py` to teach the local visual cache."
                )
        else:
            if all(not (row.get("ean") or "").strip() for row in signature_rows):
                st.warning(
                    "Cached signatures found but EAN is missing — re-run `python3 ft-05.py` "
                    "to refresh the local visual cache."
                )
            st.dataframe(
                pd.DataFrame(signature_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "sku_id": st.column_config.TextColumn("SKU ID"),
                    "ean": st.column_config.TextColumn("EAN (13-digit barcode)"),
                    "feature_hash": st.column_config.TextColumn("Feature Hash"),
                },
            )

        st.divider()
        offline_log_rows = _load_offline_detection_log_rows(str(EDGE_AI_BUFFER_PATH))
        st.markdown("#### Pending Offline Scans")
        st.caption(f"Source: `{EDGE_AI_BUFFER_PATH.name}`")
        if not offline_log_rows:
            if not buffer_file_exists:
                st.info(
                    "WAL buffer queue is empty — `offline_detection_buffer_ft05.db` was not found. "
                    "Run `python3 ft-05.py` to append an offline detection row."
                )
            else:
                st.info("WAL buffer queue is empty.")
        else:
            st.dataframe(
                pd.DataFrame(offline_log_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "timestamp": st.column_config.TextColumn("Timestamp"),
                    "sku_id": st.column_config.TextColumn("SKU ID"),
                    "detected_quantity": st.column_config.NumberColumn("Detected Qty"),
                    "status": st.column_config.TextColumn("Status"),
                },
            )
    else:
        with edge_col2:
            st.metric("Cached Visual Signatures", "—")
        with edge_col3:
            st.metric("Pending Offline Scans", "—")
        st.caption(
            "SQLite WAL reads are deferred until you load this tab's buffers "
            "(keeps other tabs responsive)."
        )

with tab5:
    st.session_state[_DASHBOARD_ACTIVE_TAB_KEY] = TAB_API_BOUNCER
    st.subheader("API Bouncer — Network Health & Ingress Controls")

    if st.button("Refresh bouncer telemetry", key="load_bouncer_tab"):
        st.session_state[_BOUNCER_TAB_LOADED_KEY] = True
        st.rerun()

    if st.session_state.get(_BOUNCER_TAB_LOADED_KEY, False):
        health = fetch_bouncer_health()
        rejections = fetch_bouncer_rejections()
        reconciliations = fetch_bouncer_reconciliations()

        if health:
            h1, h2, h3, h4 = st.columns(4)
            with h1:
                st.metric("Middleware Status", health.get("status", "unknown").upper())
            with h2:
                st.metric("Rejections (1h)", health.get("rejections_last_hour", 0))
            with h3:
                st.metric("Reconciliations", health.get("reconciliations_total", 0))
            with h4:
                st.metric("CV Rate Limit / min", health.get("rate_limit_per_minute", "—"))

            st.markdown("#### Throttle & Integrity Limits")
            limits_col1, limits_col2, limits_col3 = st.columns(3)
            with limits_col1:
                st.metric("Fill Rate Limit / min", health.get("fill_rate_limit_per_minute", "—"))
            with limits_col2:
                st.metric("Max Payload (bytes)", health.get("max_body_bytes", "—"))
            with limits_col3:
                st.metric("Edge Token Armed", "Yes" if health.get("edge_token_configured") else "No")
            st.caption(f"WAL audit buffer: `{health.get('wal_buffer_path', 'bouncer_audit.db')}`")
        else:
            st.warning(
                "Unable to reach bouncer health endpoint. Ensure the FastAPI backend is running "
                "and `API_BASE_URL` resolves (Docker Compose sets this to the backend service)."
            )

        st.divider()
        st.markdown("#### Active API Rejections")
        if rejections:
            st.dataframe(
                pd.DataFrame(rejections),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No rejected ingress payloads recorded in the bouncer WAL buffer.")

        st.divider()
        st.markdown("#### Live Reconciliation Log")
        if st.button("Purge Reconciliation Log", type="primary", key="purge_bouncer_reconciliation_log"):
            try:
                response = requests.delete(f"{API_BASE_URL}/bouncer/purge", timeout=5)
                if response.status_code == 200:
                    st.rerun()
                else:
                    st.error(
                        f"Purge failed ({response.status_code}): {response.text}"
                    )
            except requests.exceptions.RequestException as exc:
                st.error(f"Purge failed: {exc}")
        if reconciliations:
            render_bouncer_reconciliation_dashboard(reconciliations)
        else:
            st.info(
                "No CV reconciliations yet. Run `python3 tests/simulate_cv_traffic.py` "
                "against the integrated middleware."
            )
    else:
        st.caption(
            "Click **Refresh bouncer telemetry** to fetch network health, rejections, "
            "and throttle limits from the FastAPI middleware."
        )

with tab6:
    st.session_state[_DASHBOARD_ACTIVE_TAB_KEY] = TAB_SHOPFLOOR_SCENARIOS
    st.subheader("Shopfloor Scenarios — Manual Edge Injection")
    st.caption(
        "Inject retail edge scenarios into the API Bouncer reconciliation log. "
        "Spline 3D state is prepared on each successful inject (no visual embed yet)."
    )

    scenario_choice = st.radio(
        "Select scenario to inject",
        [
            "Scenario A: Shelf Damage (Torn Multipack)",
            "Scenario B: Abandoned Promotional Flattop",
            "Scenario C: Messy Fill (Planogram Mismatch)",
        ],
        key="shopfloor_scenario_choice",
    )

    if scenario_choice.startswith("Scenario A"):
        st.markdown("#### Shelf Damage (Torn Multipack)")
        if "scenario_a_max_capacity" not in st.session_state:
            _default_shelf = _SHELF_PRODUCT_NAMES[0]
            st.session_state.scenario_a_max_capacity = _shelf_sku_max_capacity(_default_shelf)
        if "filled_qty" not in st.session_state:
            st.session_state.filled_qty = st.session_state.scenario_a_max_capacity
        if "damaged_qty" not in st.session_state:
            st.session_state.damaged_qty = 0

        st.selectbox(
            "Shelf SKU",
            _SHELF_PRODUCT_NAMES,
            key="shopfloor_a_sku",
            on_change=_sync_scenario_a_on_sku_change,
        )
        shelf_name = st.session_state.shopfloor_a_sku
        shelf_row = _CATALOG_BY_NAME[shelf_name]
        max_capacity = _shelf_sku_max_capacity(shelf_name)
        st.session_state.scenario_a_max_capacity = max_capacity

        fill_col, dmg_col = st.columns(2)
        with fill_col:
            st.number_input(
                "Total Units Filled",
                min_value=0,
                max_value=max_capacity,
                key="filled_qty",
                on_change=_scenario_a_update_fill,
            )
        with dmg_col:
            st.number_input(
                "Damages Detected",
                min_value=0,
                max_value=max_capacity,
                key="damaged_qty",
                on_change=_scenario_a_update_damage,
            )
        if st.button("Inject Scenario A", key="shopfloor_inject_a"):
            response, trx_id = inject_custom_payload(
                ean=shelf_row["ean"],
                product_name=shelf_name,
                exception_type="TORN_MULTIPACK",
                total_units=int(st.session_state.filled_qty),
                damaged_units=int(st.session_state.damaged_qty),
                fixture_id="CAM-AISLE-04",
            )
            if response.status_code == 200:
                st.session_state.active_ean = [shelf_row["ean"]]
                st.session_state.fixture_type = ["SHELF"]
                st.session_state.sku_alert = 1
                st.toast(f"✅ Injected {trx_id} — shelf damage recorded.")
            else:
                st.error(f"Inject failed ({response.status_code}): {response.text}")

    elif scenario_choice.startswith("Scenario B"):
        st.markdown("#### Abandoned Promotional Flattop")
        flattop_id = st.selectbox("Flattop ID", ["FT-01", "FT-02"], key="shopfloor_b_flattop")
        selected_names = st.multiselect(
            "SKUs on flattop — cross-merchandising allowed (max 3)",
            _ALL_PRODUCT_NAMES,
            max_selections=3,
            key="shopfloor_b_skus",
        )
        if st.button("Inject Scenario B", key="shopfloor_inject_b"):
            if not selected_names:
                st.warning("Select at least one flattop SKU.")
            else:
                trx_ids: list[str] = []
                errors: list[str] = []
                for name in selected_names:
                    row = _CATALOG_BY_NAME[name]
                    response, trx_id = inject_custom_payload(
                        ean=row["ean"],
                        product_name=name,
                        exception_type="ABANDONED_FLATTOP",
                        total_units=int(row["bom_units"]),
                        damaged_units=0,
                        fixture_id=flattop_id,
                    )
                    if response.status_code == 200:
                        trx_ids.append(trx_id)
                    else:
                        errors.append(f"{name}: {response.status_code} {response.text}")
                if trx_ids:
                    st.session_state.active_ean = [_CATALOG_BY_NAME[selected_names[0]]["ean"]]
                    st.session_state.fixture_type = [flattop_id]
                    st.session_state.sku_alert = 1
                    st.toast(
                        f"✅ Injected {len(trx_ids)} flattop event(s): {', '.join(trx_ids)}"
                    )
                for err in errors:
                    st.error(err)

    else:
        st.markdown("#### Messy Fill (Planogram Mismatch)")
        actual_name = st.selectbox(
            "Actual Item Detected",
            _ALL_PRODUCT_NAMES,
            key="shopfloor_c_actual",
        )
        expected_name = st.selectbox(
            "Expected Item for this Slot",
            _ALL_PRODUCT_NAMES,
            key="shopfloor_c_expected",
        )
        actual_row = _CATALOG_BY_NAME[actual_name]
        expected_row = _CATALOG_BY_NAME[expected_name]
        case_max = int(actual_row["bom_units"])
        lost_col, fill_col = st.columns(2)
        with lost_col:
            units_lost = st.number_input(
                "Units Lost",
                min_value=0,
                max_value=case_max,
                value=0,
                key="shopfloor_c_lost",
            )
        with fill_col:
            max_fill = max(0, case_max - units_lost)
            units_filled = st.number_input(
                "Units Filled",
                min_value=0,
                max_value=max_fill,
                value=max_fill,
                key="shopfloor_c_fill",
            )
        if st.button("Inject Scenario C", key="shopfloor_inject_c"):
            response, trx_id = inject_custom_payload(
                ean=actual_row["ean"],
                product_name=actual_name,
                exception_type="PLANOGRAM_MISMATCH",
                total_units=int(units_filled),
                damaged_units=0,
                units_lost=int(units_lost),
                expected_ean=expected_row["ean"],
                fixture_id="CAM-AISLE-04",
            )
            if response.status_code == 200:
                st.session_state.active_ean = [actual_row["ean"]]
                st.session_state.fixture_type = ["SHELF"]
                st.session_state.sku_alert = 2
                st.toast(f"✅ Injected {trx_id} — planogram mismatch recorded.")
            else:
                st.error(f"Inject failed ({response.status_code}): {response.text}")

    with st.expander("Spline prep state (read-only preview)"):
        st.write(
            {
                "active_ean": st.session_state.get("active_ean", []),
                "fixture_type": st.session_state.get("fixture_type", ["SHELF"]),
                "sku_alert": st.session_state.get("sku_alert", 0),
            }
        )

st.divider()

tasks = build_tasks(live_containers)
grid_cols = st.columns(3)

for index, task in enumerate(tasks):
    with grid_cols[index % 3]:
        render_execution_telemetry_card(task)
