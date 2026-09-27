import streamlit as st

# 1. Page Configuration
st.set_page_config(
    page_title="Neurolabs Edge: Inventory Reconciliation",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Main Title
st.title("WIP Exception Engine")
st.markdown("Enterprise Dashboard for Real-Time Execution Tracking & Anomaly Detection")

# 2. Top Header Section: Global Metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="Active CV Out-of-Stocks", value=1, delta="Critical", delta_color="inverse")
with col2:
    st.metric(label="Detected Phantom Drift Units", value=9, delta="Shrink Risk", delta_color="inverse")
with col3:
    st.metric(label="Pending Edge Tasks", value=2, delta="Unresolved")

# Visual Divider
st.divider()

# 3. Main Content Sections
left_col, right_col = st.columns(2)

# ==========================================
# LEFT COLUMN: Scenario 1 - The Chaotic Frontline
# ==========================================
with left_col:
    st.subheader("Execution Telemetry: FT-02")
    st.caption("Last Known State: ABANDONED_MID_SHIFT | Zone: Aisle 4")
    
    st.markdown("**SKU Profile:** `BAKED-BEANS-6PK`")
    
    # Internal columns for clean metric display
    metrics_c1, metrics_c2 = st.columns(2)
    
    with metrics_c1:
        st.metric("Expected Quantity", 12)
        st.metric("Sent to Backstock", 2)
        
    with metrics_c2:
        st.metric("Worked to Shelf", 6)
        st.metric("Dumped Unworked", 1)
        
    st.markdown("---")
    
    # Warning block for the phantom drift
    st.warning("⚠️ **PHANTOM DRIFT:** 3 units of 'BAKED-BEANS-6PK' are missing and completely unaccounted for in system telemetry.")

# ==========================================
# RIGHT COLUMN: Scenario 2 - Blind Spot Detection
# ==========================================
with right_col:
    st.subheader("Vision Task: FT-01")
    st.caption("Last Known State: IN_PROGRESS_SHOPFLOOR | Zone: Aisle 2")
    
    st.markdown("**SKU Profile:** `CHOCO-BISCUITS-6PK`")
    
    # Calculate state
    initial_load = 12
    cv_fill_events = 6
    unaccounted_variance = initial_load - cv_fill_events
    
    # Initialize session state for resolution tracking
    if 'variance_resolved' not in st.session_state:
        st.session_state.variance_resolved = False
        st.session_state.resolution_message = ""
        st.session_state.confirmed_units = 0
    
    # Internal columns for clean metric display
    metrics_c3, metrics_c4 = st.columns(2)
    
    with metrics_c3:
        st.metric("Expected Quantity", initial_load)
        
    with metrics_c4:
        st.metric("CV Fill Events", cv_fill_events)
        if st.session_state.variance_resolved:
            st.metric("Confirmed in Backstock", st.session_state.confirmed_units)
        
    st.markdown("---")
    
    if st.session_state.variance_resolved:
        st.success(f"✅ **Variance Cleared:** {st.session_state.resolution_message}")
        st.metric("Unaccounted Variance", 0)
    else:
        st.metric("Unaccounted Variance", unaccounted_variance, delta="-6 untracked", delta_color="inverse")
        st.markdown("<br>", unsafe_allow_html=True)
        
        if unaccounted_variance > 0:
            st.warning(
                f"⚠️ **ACTION REQUIRED:** {unaccounted_variance} units of CHOCO-BISCUITS-6PK are unaccounted for. "
                "System suspects untracked backstock routing."
            )
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Interactive Resolution Button
            if st.button(f"Confirm {unaccounted_variance} Units in Backstock", type="primary", use_container_width=True):
                st.session_state.variance_resolved = True
                st.session_state.resolution_message = "Un-shelved stock presence confirmed in backroom."
                st.session_state.confirmed_units = unaccounted_variance
                # Underlying state machine would log these units as CONFIRMED_BACKSTOCK here
                st.rerun()
        else:
            st.success("✅ **Task Complete / Fully Reconciled:** All units successfully tracked.")
