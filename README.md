# WIP Exception Engine

The **WIP (Work In Progress) Exception Engine** is an enterprise-grade solution designed to bridge the gap between shelf-edge Computer Vision (CV) out-of-stock detections and real-time inventory telemetry. By reconciling visual shelf data with backroom staging and inventory manifests, the engine identifies and tracks execution anomalies, phantom drift, and shrink risks in real-time.

## Overview

In modern retail and warehouse environments, what the system believes is on the shelf often diverges from reality. The WIP Exception Engine solves this by:

1. **Integrating Computer Vision:** Capturing real-time shelf-edge out-of-stock events.
2. **Tracking Inventory Telemetry:** Monitoring the movement of Work In Progress (WIP) containers (e.g., LPNs, totes, pallets) from backroom staging to the shop floor.
3. **Reconciling Data Streams:** Automatically correlating expected quantities with actual shelf availability to detect discrepancies like "Phantom Drift" (items that are lost or misplaced between the backroom and the shelf).

## Features

- **Enterprise Dashboard:** Built with Streamlit, providing real-time execution tracking, anomaly detection, and global metrics.
- **WIP Container Tracking:** Track the state, zone, and item manifests of individual containers (e.g., `WipContainer`, `ContainerItem`).
- **Anomaly & Shrink Detection:** Identify potential shrink risks and phantom drift units when expected inventory does not match CV-detected shelf reality.
- **RESTful API Routers:** Extensible routing architecture for integrating external CV and telemetry data sources.

## Repository Structure

- `dashboard.py`: Main Streamlit application providing the enterprise dashboard.
- `models/`: Domain models including `WipContainer` and `ContainerItem` state management.
- `routers/`: API route handlers for external integrations.
- `test_drift.py`: Testing and simulation script for modeling "Phantom Drift" and anomalous inventory scenarios.

## Getting Started

### Prerequisites

- Python 3.8+
- [Streamlit](https://streamlit.io/)

### Installation

Clone the repository and install the required dependencies (if a `requirements.txt` is provided, otherwise ensure Streamlit is installed):

```bash
pip install streamlit
```

### Running the Dashboard

Launch the enterprise dashboard using Streamlit:

```bash
streamlit run dashboard.py
```

### Running Tests

Execute the drift scenario tests to see the exception engine in action:

```bash
python test_drift.py
```

## Architecture Notes

The system leverages a state-driven approach for containers. Each WIP container transitions through various states and zones (e.g., Backroom Staging -> Shop Floor), updating its item manifest as it is worked. If a CV out-of-stock event persists despite a container being marked as "worked" for that SKU, the engine flags a discrepancy for immediate investigation.
