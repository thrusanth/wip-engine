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
/* Target Column 1 (All Found - Green) */
div[data-testid="stHorizontalBlock"]:has(button) > div:nth-child(1) button {
    background-color: #198754 !important;
    border-color: #198754 !important;
    color: #ffffff !important;
}
div[data-testid="stHorizontalBlock"]:has(button) > div:nth-child(1) button:hover {
    background-color: #157347 !important;
    border-color: #146c43 !important;
}

/* Target Column 2 (Not Present - Red) */
div[data-testid="stHorizontalBlock"]:has(button) > div:nth-child(2) button {
    background-color: #dc3545 !important;
    border-color: #dc3545 !important;
    color: #ffffff !important;
}
div[data-testid="stHorizontalBlock"]:has(button) > div:nth-child(2) button:hover {
    background-color: #bb2d3b !important;
    border-color: #b02a37 !important;
}

/* Target Column 3 (Partial - Blue) */
div[data-testid="stHorizontalBlock"]:has(button) > div:nth-child(3) button {
    background-color: #0d6efd !important;
    border-color: #0d6efd !important;
    color: #ffffff !important;
}
div[data-testid="stHorizontalBlock"]:has(button) > div:nth-child(3) button:hover {
    background-color: #0b5ed7 !important;
    border-color: #0a58ca !important;
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

def submit_resolution(container_id, sku, resolution_type, recovered_units=0):
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
        st.rerun()
    except requests.exceptions.Timeout:
        st.warning(f"Backend API timed out while submitting resolution for container {container_id}.")
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to submit resolution due to connection error: {e}")
        st.stop()

# Fetch data on load
try:
    telemetry_data = fetch_telemetry()
    
    if telemetry_data and "metrics" in telemetry_data and "pending_delivery_cages" in telemetry_data["metrics"]:
        metrics = telemetry_data["metrics"]
        containers = telemetry_data.get("containers", {})
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

tab1, tab2 = st.tabs(["System Overview", "Telemetry & Exceptions"])

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
            submit_resolution(container_id, sku, "all", units)

    with ctrl_cols[1]:
        if st.button(
            "Not Present (0)",
            key=_operational_widget_key("not_present", container_id, sku),
            use_container_width=True,
        ):
            submit_resolution(container_id, sku, "none", 0)

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
                submit_resolution(container_id, sku, "partial", partial_qty)


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

# Create a 2-column grid for the dashboard
grid_cols = st.columns(2)

for index, task in enumerate(tasks):
    # Alternate between the left and right columns
    with grid_cols[index % 2]:
        render_execution_telemetry_card(task)
