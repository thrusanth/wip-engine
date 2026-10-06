import os

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://backend:8000/api/v1")
API_KEY = os.getenv("WIP_API_KEY", "dev-wip-engine-key")

# 1. Page Configuration
st.set_page_config(
    page_title="WIP Exception Engine: Inventory Reconciliation",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
_USE_CACHED_TELEMETRY_KEY = "dashboard_use_cached_telemetry"

OFFLINE_FILL_AUDIT_SKU = "PASTA-CASE-12"
OFFLINE_FILL_AUDIT_ACTION = "fill"
OFFLINE_FILL_AUDIT_QUANTITY = 12


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
    else:
        telemetry_data = fetch_telemetry()

        if telemetry_data and "metrics" in telemetry_data and "pending_delivery_cages" in telemetry_data["metrics"]:
            metrics = telemetry_data["metrics"]
            containers = telemetry_data.get("containers", {})
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

    st.session_state[_DASHBOARD_CONTAINERS_KEY] = containers
    st.session_state[_DASHBOARD_METRICS_KEY] = metrics
    st.session_state[_DASHBOARD_OFFLINE_FILLS_KEY] = offline_fill_audit
    st.session_state[_DASHBOARD_INVENTORY_GAP_KEY] = inventory_gap_audit
    st.session_state[_DASHBOARD_OFFLINE_GAP_EXCEPTIONS_KEY] = offline_gap_exceptions
except Exception as e:
    st.error(f"API Connection Error: {e}")
    st.stop()

# ---------------------------------------------------------
# Top Header Section: Global Metrics
# ---------------------------------------------------------
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric(label="Pending Delivery Cages", value=metrics["pending_delivery_cages"], delta="Awaiting Breakdown", delta_color="off")
with col2:
    st.metric(label="Active Flattops", value=metrics["active_flattops"], delta="Live Manifests", delta_color="off")
with col3:
    st.metric(label="Detected Phantom Drift Units", value=metrics["detected_phantom_drift"], delta="Shrink Risk", delta_color="inverse")
with col4:
    st.metric(label="Daily Shrink Cost", value=f"£{metrics['daily_shrink_cost']:,.2f}", delta="Revenue Lost", delta_color="inverse")
with col5:
    if metrics["pending_edge_tasks"] > 0:
        st.metric(label="Pending Edge Tasks", value=metrics["pending_edge_tasks"], delta="Action Required", delta_color="inverse")
    else:
        st.metric(label="Pending Edge Tasks", value=metrics["pending_edge_tasks"], delta="All Tasks Cleared", delta_color="normal")

telemetry_rows = []
for container_id, container in containers.items():
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

tab1, tab2, tab3 = st.tabs(["System Overview", "Telemetry & Exceptions", "Offline Fill"])

with tab1:
    st.markdown(
        "High-level operational charts and trend summaries will appear here. "
        "Use the flattop execution cards below for live reconciliation workflows."
    )

with tab2:
    st.subheader("Live Execution Telemetry")
    telemetry_df = pd.DataFrame(telemetry_rows)
    telemetry_df = telemetry_df[telemetry_df["Drift"] != 0].sort_values(
        "Drift", ascending=False
    )
    st.dataframe(telemetry_df, use_container_width=True, hide_index=True)

with tab3:
    st.markdown(
        "Post-blackout recovery review — synced offline fills and partial-fill gap exceptions. "
        "Live shop-floor telemetry remains on **Telemetry & Exceptions**."
    )

    st.subheader("Post-Blackout Offline Fill Audit")
    st.caption(
        "Central ledger view of edge-buffer fills replayed after connectivity returns "
        "(full case syncs such as PASTA-CASE-12)."
    )

    show_all_offline_fills = st.checkbox(
        "Show all synced offline fills (disable to focus pasta case scenario)",
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

    if audit_rows:
        audit_df = pd.DataFrame(audit_rows)
        display_df = audit_df.rename(
            columns={
                "timestamp": "Timestamp",
                "sku": "SKU",
                "name": "Product Name",
                "quantity": "Quantity",
                "action": "Action",
                "sync_status": "Sync Status",
            }
        )
        column_order = [
            "Timestamp",
            "SKU",
            "Product Name",
            "Quantity",
            "Action",
            "Sync Status",
        ]
        display_df = display_df[[col for col in column_order if col in display_df.columns]]
        display_df = display_df.sort_values("Timestamp", ascending=False)

        total_units = int(display_df["Quantity"].sum()) if "Quantity" in display_df.columns else 0
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        with summary_col1:
            st.metric("Ledger Events", len(display_df))
        with summary_col2:
            st.metric("Total Units Reconciled", total_units)
        with summary_col3:
            if not show_all_offline_fills:
                target_met = total_units >= OFFLINE_FILL_AUDIT_QUANTITY
                st.metric(
                    "Pasta Case Target (12)",
                    f"{total_units} / {OFFLINE_FILL_AUDIT_QUANTITY}",
                    delta="Verified" if target_met else "Pending",
                    delta_color="normal" if target_met else "inverse",
                )
            else:
                st.metric("Distinct SKUs", display_df["SKU"].nunique())

        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info(
            "No synced offline fill events in the central ledger yet. "
            f"Run `python3 ft-03.py` (Scenario 1) after a blackout to replay "
            f"{OFFLINE_FILL_AUDIT_SKU} ({OFFLINE_FILL_AUDIT_ACTION}) events."
        )

    st.divider()
    st.subheader("Offline Partial Fill & Gap Scan Exceptions")
    st.caption(
        "Partial offline shelf fills with unlogged backstock variance. "
        "Review gap-scan recommendations alongside synced fill rows above."
    )

    gap_exception_by_sku = {
        exc.get("sku"): exc for exc in offline_gap_exceptions if exc.get("sku")
    }

    if inventory_gap_audit:
        gap_rows = []
        for row in inventory_gap_audit:
            sku = row.get("sku", "")
            exc = gap_exception_by_sku.get(sku, {})
            gap_rows.append(
                {
                    "timestamp": row.get("timestamp", ""),
                    "sku": sku,
                    "name": row.get("name") or sku,
                    "expected_units": row.get("expected_units"),
                    "recorded_units": row.get("recorded_units"),
                    "variance_delta": row.get("variance_delta"),
                    "missing_units": row.get("unlogged_backstock_units"),
                    "action": row.get("action", ""),
                    "status": row.get("status", "Gap Scan Recommended"),
                    "exception_message": exc.get("message", ""),
                }
            )

        gap_df = pd.DataFrame(gap_rows)
        gap_display = gap_df.rename(
            columns={
                "timestamp": "Timestamp",
                "sku": "SKU",
                "name": "Product Name",
                "expected_units": "Expected Units",
                "recorded_units": "Recorded Shelf Units",
                "variance_delta": "Variance Delta",
                "missing_units": "Unlogged Backstock (Missing)",
                "action": "Action",
                "status": "Status",
                "exception_message": "Exception Detail",
            }
        )
        gap_column_order = [
            "Timestamp",
            "SKU",
            "Product Name",
            "Expected Units",
            "Recorded Shelf Units",
            "Variance Delta",
            "Unlogged Backstock (Missing)",
            "Action",
            "Status",
            "Exception Detail",
        ]
        gap_display = gap_display[
            [col for col in gap_column_order if col in gap_display.columns]
        ].sort_values("Timestamp", ascending=False)

        gap_col1, gap_col2, gap_col3 = st.columns(3)
        with gap_col1:
            st.metric("Gap Scan Cases", len(gap_display))
        with gap_col2:
            st.metric(
                "Total Missing Units",
                int(gap_display["Unlogged Backstock (Missing)"].sum())
                if "Unlogged Backstock (Missing)" in gap_display.columns
                else 0,
            )
        with gap_col3:
            st.metric("Open Gap Scans", gap_display["SKU"].nunique())

        st.dataframe(gap_display, use_container_width=True, hide_index=True)
    elif offline_gap_exceptions:
        exc_df = pd.DataFrame(offline_gap_exceptions)
        exc_display = exc_df.rename(
            columns={
                "sku": "SKU",
                "units": "Unlogged Backstock (Missing)",
                "status": "Status",
                "message": "Exception Detail",
                "zone": "Zone",
            }
        )
        st.dataframe(exc_display, use_container_width=True, hide_index=True)
    else:
        st.info(
            "No offline partial-fill gap exceptions in the central ledger. "
            "Run `python3 ft-03.py` (Scenario 2) to simulate RICE-CASE-6 "
            "(Expected 6, Recorded 4, Delta -2)."
        )

st.divider()

# ---------------------------------------------------------
# Main Content Sections
# ---------------------------------------------------------
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
    """True when the SKU still has phantom drift or unaccounted variance to resolve."""
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


FLATTOP_CARD_CONTAINER_KWARGS = {"border": True, "width": "stretch"}


def render_execution_telemetry_card(task: dict) -> None:
    """Strict FT-02-style template: metrics, variance alerts, and 3-column control deck."""
    container_data = _container_view_from_task(task)
    sku_data = _sku_view_from_task(task)
    product_name = sku_data.get("name", sku_data["sku"])

    with st.container(**FLATTOP_CARD_CONTAINER_KWARGS):
        st.subheader(f"Execution Telemetry: {container_data['id']}")
        st.caption(f"Last Known State: {container_data['status']} | Zone: {container_data['zone']}")
        st.markdown(
            f"**SKU Profile:** {product_name}  \n"
            f"`{sku_data['sku']}`  \n"
            f"**EAN:** `{sku_data.get('ean', '')}`"
        )

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


tasks = build_tasks(containers)

# Create a 3-column grid for a more compact dashboard layout
grid_cols = st.columns(3)

for index, task in enumerate(tasks):
    # Alternate cards across the 3 columns
    with grid_cols[index % 3]:
        render_execution_telemetry_card(task)
