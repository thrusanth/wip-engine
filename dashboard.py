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
    st.subheader("Execution Telemetry: FLT-8829")
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
# RIGHT COLUMN: Scenario 2 - The Ghost Case
# ==========================================
with right_col:
    st.subheader("Vision Exception Task: FT-01")
    st.caption("Last Known State: IN_PROGRESS_SHOPFLOOR | Zone: Aisle 2")
    
    st.markdown("**SKU Profile:** `CHOCO-BISCUITS-6PK`")
    
    # Empty space for alignment
    st.markdown("<br>", unsafe_allow_html=True)
    
    # High-priority alert bridging CV and the WIP API
    st.error(
        "🚨 **COMPUTER VISION:** Aisle 2 Shelf Empty. "
        "WIP API: 6 units of CHOCO-BISCUITS-6PK abandoned off-camera."
    )
    
    # Empty space for alignment before the button
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Simulated Action Button
    if st.button("Dispatch Task: Retrieve Ghost Case from Backroom", type="primary", use_container_width=True):
        st.success("✅ **Task Dispatched successfully!** A shift leader has been notified via their Zebra device.")
