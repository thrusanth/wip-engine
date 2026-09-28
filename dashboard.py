import streamlit as st
import requests
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://backend:8000/api/v1")

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
        response = requests.post(f"{API_BASE_URL}/events/resolve", json=payload, timeout=3)
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

# Visual Divider
st.divider()

# ---------------------------------------------------------
# Main Content Sections
# ---------------------------------------------------------
left_col, middle_col, right_col = st.columns(3)

# ==========================================
# LEFT COLUMN: Scenario 1 - The Chaotic Frontline (FT-02)
# ==========================================
with left_col:
    with st.container(border=True):
        ft2_data = containers.get("FT-02")
        if ft2_data:
            sku_data = ft2_data["skus"][0]
            st.subheader(f"Execution Telemetry: {ft2_data['id']}")
            st.caption(f"Last Known State: {ft2_data['status']} | Zone: {ft2_data['zone']}")
            
            st.markdown(f"**SKU Profile:** `{sku_data['sku']}`")
            
            # Internal columns for clean metric display
            metrics_c1, metrics_c2 = st.columns(2)
            
            with metrics_c1:
                st.metric("Expected Quantity", sku_data["expected"])
                st.metric("Sent to Backstock", sku_data["backstock"])
                
            with metrics_c2:
                st.metric("Worked to Shelf", sku_data["worked"])
                st.metric("Phantom Drift", sku_data["drift"])
                
            st.markdown("---")
            
            if sku_data["is_resolved"]:
                if sku_data["resolution_type"] == "all":
                    st.success("✅ **Resolved:** All 4 units recovered and accounted for.")
                elif sku_data["resolution_type"] == "none":
                    st.error("🚨 **Shrink Confirmed:** 4 units officially lost/unaccounted.")
                elif sku_data["resolution_type"] == "partial":
                    st.warning(f"⚠️ **Partial Resolution:** {sku_data['recovered_units']} found, {sku_data['shrink_confirmed']} confirmed as shrink.")
            else:
                # Warning block for the phantom drift
                st.warning(f"⚠️ **PHANTOM DRIFT:** {sku_data['drift']} units of '{sku_data['sku']}' are missing and completely unaccounted for in system telemetry.")
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # Interactive Resolution Buttons for FT-02
                col_ft2_1, col_ft2_2, col_ft2_3 = st.columns(3)
                with col_ft2_1:
                    if st.button(f"All Found ({sku_data['drift']})", key="ft2_all"):
                        submit_resolution(ft2_data["id"], sku_data["sku"], "all", sku_data["drift"])
                with col_ft2_2:
                    if st.button(f"Not Present (0)", key="ft2_none"):
                        submit_resolution(ft2_data["id"], sku_data["sku"], "none", 0)
                with col_ft2_3:
                    # Toggle for partial input
                    if 'ft2_show_partial' not in st.session_state:
                        st.session_state.ft2_show_partial = False
                        
                    if st.button("Partial Found...", key="ft2_partial"):
                        st.session_state.ft2_show_partial = not st.session_state.ft2_show_partial
                        
                if st.session_state.get('ft2_show_partial', False):
                    st.markdown("<br>", unsafe_allow_html=True)
                    partial_col1, partial_col2 = st.columns([2, 1])
                    with partial_col1:
                        partial_qty = st.number_input("Quantity Recovered?", min_value=1, max_value=sku_data['drift']-1, value=1)
                    with partial_col2:
                        st.markdown("<br>", unsafe_allow_html=True) # Alignment
                        if st.button("Confirm Partial", type="primary", key="ft2_confirm_partial"):
                            submit_resolution(ft2_data["id"], sku_data["sku"], "partial", partial_qty)

# ==========================================
# MIDDLE COLUMN: Scenario 2 - Blind Spot Detection (FT-01)
# ==========================================
with middle_col:
    with st.container(border=True):
        ft1_data = containers.get("FT-01")
        if ft1_data:
            sku_data = ft1_data["skus"][0]
            st.subheader(f"Vision Task: {ft1_data['id']}")
            st.caption(f"Last Known State: {ft1_data['status']} | Zone: {ft1_data['zone']}")
            
            st.markdown(f"**SKU Profile:** `{sku_data['sku']}`")
            
            # Internal columns for clean metric display
            metrics_c3, metrics_c4 = st.columns(2)
            
            with metrics_c3:
                st.metric("Expected Quantity", sku_data["expected"])
                
            with metrics_c4:
                st.metric("CV Fill Events", sku_data["cv_filled"])
                if sku_data["is_resolved"]:
                    st.metric("Confirmed in Backstock", sku_data["recovered_units"])
                
            st.markdown("---")
            
            if sku_data["is_resolved"]:
                st.success("✅ **Variance Cleared:** Un-shelved stock presence confirmed in backroom.")
                st.metric("Unaccounted Variance", 0)
            else:
                st.metric("Unaccounted Variance", sku_data["variance"], delta="-6 untracked", delta_color="inverse")
                st.markdown("<br>", unsafe_allow_html=True)
                
                if sku_data["variance"] > 0:
                    st.warning(
                        f"⚠️ **ACTION REQUIRED:** {sku_data['variance']} units of {sku_data['sku']} are unaccounted for. "
                        "System suspects untracked backstock routing."
                    )
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # Interactive Resolution Button
                    if st.button(f"Confirm {sku_data['variance']} Units in Backstock", type="primary", use_container_width=True):
                        submit_resolution(ft1_data["id"], sku_data["sku"], "all", sku_data["variance"])
                else:
                    st.success("✅ **Task Complete / Fully Reconciled:** All units successfully tracked.")

# ==========================================
# RIGHT COLUMN: Scenario 3 - High Value Fast-Moving SKU (FT-03)
# ==========================================
with right_col:
    with st.container(border=True):
        ft3_data = containers.get("FT-03")
        if ft3_data:
            sku_data = ft3_data["skus"][0]
            st.subheader(f"Vision Task: {ft3_data['id']}")
            st.caption(f"Last Known State: {ft3_data['status']} | Zone: {ft3_data['zone']}")
            
            st.markdown(f"**SKU Profile:** `{sku_data['sku']}`")
            
            # Internal columns for clean metric display
            metrics_c5, metrics_c6 = st.columns(2)
            
            with metrics_c5:
                st.metric("Expected Quantity", sku_data["expected"])
                
            with metrics_c6:
                st.metric("CV Fill Events", sku_data["cv_filled"])
                st.metric("Confirmed in Backstock", sku_data["confirmed_backstock"])
                
            st.markdown("---")
            
            if sku_data["variance"] == 0:
                st.success("✅ **Variance Cleared:** Un-shelved stock presence confirmed in backroom.")
                st.metric("Unaccounted Variance", 0)
            else:
                st.metric("Unaccounted Variance", sku_data["variance"])
                st.warning("⚠️ **ACTION REQUIRED:** Discrepancy detected.")
