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


PHANTOM_RESOLUTION_BUTTON_STYLES = """
<style>
/* Column 1: All Found (Green) */
div.stHorizontalBlock > div:nth-child(1) button[kind="secondary"],
div[data-testid="column"]:nth-of-type(1) button {
    background-color: #198754 !important;
    border-color: #198754 !important;
    color: #ffffff !important;
}

/* Column 2: Not Present (Red) */
div.stHorizontalBlock > div:nth-child(2) button[kind="secondary"],
div[data-testid="column"]:nth-of-type(2) button {
    background-color: #dc3545 !important;
    border-color: #dc3545 !important;
    color: #ffffff !important;
}

/* Column 3: Partial (Blue) */
div.stHorizontalBlock > div:nth-child(3) button[kind="secondary"],
div[data-testid="column"]:nth-of-type(3) button {
    background-color: #0d6efd !important;
    border-color: #0d6efd !important;
    color: #ffffff !important;
}
</style>
"""


def render_phantom_resolution_actions(container_data, sku_data, prefix: str) -> None:
    """Colored primary buttons for phantom drift resolution (single action row)."""
    drift = sku_data["drift"]
    partial_flag = f"{prefix}_show_partial"
    if partial_flag not in st.session_state:
        st.session_state[partial_flag] = False

    st.markdown(PHANTOM_RESOLUTION_BUTTON_STYLES, unsafe_allow_html=True)
    col_1, col_2, col_3 = st.columns(3)
    with col_1:
        if st.button(
            f"All Found ({drift})",
            key=f"{prefix}_all",
            use_container_width=True,
        ):
            submit_resolution(container_data["id"], sku_data["sku"], "all", drift)

    with col_2:
        if st.button(
            "Not Present (0)",
            key=f"{prefix}_none",
            use_container_width=True,
        ):
            submit_resolution(container_data["id"], sku_data["sku"], "none", 0)

    with col_3:
        if st.button(
            f"Partial ({drift})",
            key=f"{prefix}_partial",
            use_container_width=True,
        ):
            st.session_state[partial_flag] = not st.session_state[partial_flag]

    if st.session_state.get(partial_flag, False):
        st.warning("Partial recovery in progress — enter quantity recovered below.")
        partial_col1, partial_col2 = st.columns([2, 1])
        with partial_col1:
            max_partial = max(1, drift - 1)
            partial_qty = st.number_input(
                "Quantity Recovered?",
                min_value=1,
                max_value=max_partial,
                value=1,
                key=f"{prefix}_partial_qty",
            )
        with partial_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Confirm Partial", type="primary", key=f"{prefix}_confirm_partial"):
                submit_resolution(
                    container_data["id"],
                    sku_data["sku"],
                    "partial",
                    partial_qty,
                )


def render_execution_telemetry_card(container_data, sku_data, card_key_prefix):
    """Execution Telemetry card body (FT-02 / FT-04 inventory lines)."""
    prefix = card_key_prefix
    product_name = sku_data.get("name", sku_data["sku"])

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
    elif sku_data["drift"] > 0:
        st.warning(
            f"⚠️ **PHANTOM DRIFT:** {sku_data['drift']} units of "
            f"'{product_name}' are missing and completely unaccounted for in system telemetry."
        )
        st.markdown("<br>", unsafe_allow_html=True)
        render_phantom_resolution_actions(container_data, sku_data, prefix)
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


def render_vision_task_ft01_card(container_data, sku_data):
    st.subheader(f"Vision Task: {container_data['id']}")
    st.caption(f"Last Known State: {container_data['status']} | Zone: {container_data['zone']}")
    st.markdown(
        f"**SKU Profile:** `{sku_data['sku']}`  \n"
        f"**EAN:** `{sku_data.get('ean', '')}`"
    )

    metrics_left, metrics_right = st.columns(2)
    with metrics_left:
        st.metric("Expected Quantity", sku_data["expected"])
    with metrics_right:
        st.metric("CV Fill Events", sku_data["cv_filled"])
        if sku_data["is_resolved"]:
            st.metric("Confirmed in Backstock", sku_data["recovered_units"])

    st.markdown("---")

    if sku_data["is_resolved"]:
        render_unaccounted_variance_metric(sku_data)
        st.success("✅ **Variance Cleared:** Un-shelved stock presence confirmed in backroom.")
    else:
        render_unaccounted_variance_metric(
            sku_data, delta="-6 untracked", delta_color="inverse"
        )
        st.markdown("<br>", unsafe_allow_html=True)

        if sku_data["variance"] > 0:
            st.warning(
                f"⚠️ **ACTION REQUIRED:** {sku_data['variance']} units of {sku_data['sku']} are unaccounted for. "
                "System suspects untracked backstock routing."
            )
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(
                f"Confirm {sku_data['variance']} Units in Backstock",
                type="primary",
                use_container_width=True,
                key="ft1_confirm_backstock",
            ):
                submit_resolution(container_data["id"], sku_data["sku"], "all", sku_data["variance"])
        else:
            st.success("✅ **Task Complete / Fully Reconciled:** All units successfully tracked.")


def render_vision_task_ft03_card(container_data, sku_data):
    st.subheader(f"Vision Task: {container_data['id']}")
    st.caption(f"Last Known State: {container_data['status']} | Zone: {container_data['zone']}")
    st.markdown(
        f"**SKU Profile:** `{sku_data['sku']}`  \n"
        f"**EAN:** `{sku_data.get('ean', '')}`"
    )

    metrics_left, metrics_right = st.columns(2)
    with metrics_left:
        st.metric("Expected Quantity", sku_data["expected"])
    with metrics_right:
        st.metric("CV Fill Events", sku_data["cv_filled"])
        st.metric("Confirmed in Backstock", sku_data["confirmed_backstock"])

    st.markdown("---")
    render_unaccounted_variance_metric(sku_data)
    if sku_data["variance"] == 0:
        st.success("✅ **Variance Cleared:** Un-shelved stock presence confirmed in backroom.")
    else:
        st.warning("⚠️ **ACTION REQUIRED:** Discrepancy detected.")


def build_flattop_card_grid(containers_dict):
    """Ordered flattop cards (Execution Telemetry + Vision Task) for grid rendering."""
    cards = []

    ft02 = containers_dict.get("FT-02")
    if ft02 and ft02.get("skus"):
        cards.append(("execution", ft02, ft02["skus"][0], "ft2"))

    ft01 = containers_dict.get("FT-01")
    if ft01 and ft01.get("skus"):
        cards.append(("vision_ft01", ft01, ft01["skus"][0], "ft1"))

    ft03 = containers_dict.get("FT-03")
    if ft03 and ft03.get("skus"):
        cards.append(("vision_ft03", ft03, ft03["skus"][0], "ft3"))

    ft04 = containers_dict.get("FT-04")
    if ft04:
        for sku_data in ft04.get("skus", []):
            line_key = sku_data["sku"].replace("-", "_").lower()
            cards.append(("execution", ft04, sku_data, f"ft4_{line_key}"))

    return cards


FLATTOP_CARD_CONTAINER_KWARGS = {"border": True, "width": "stretch"}
FLATTOP_CARDS_PER_ROW = 3


def render_flattop_card(card_kind, container_data, sku_data, key_prefix):
    with st.container(**FLATTOP_CARD_CONTAINER_KWARGS):
        if card_kind == "execution":
            render_execution_telemetry_card(container_data, sku_data, key_prefix)
        elif card_kind == "vision_ft01":
            render_vision_task_ft01_card(container_data, sku_data)
        elif card_kind == "vision_ft03":
            render_vision_task_ft03_card(container_data, sku_data)


flattop_cards = build_flattop_card_grid(containers)
for row_start in range(0, len(flattop_cards), FLATTOP_CARDS_PER_ROW):
    row_cards = flattop_cards[row_start : row_start + FLATTOP_CARDS_PER_ROW]
    row_columns = st.columns(3)
    for column_index, column in enumerate(row_columns):
        with column:
            if column_index < len(row_cards):
                render_flattop_card(*row_cards[column_index])
