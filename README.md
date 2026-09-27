# WIP Exception Engine: Inventory Reconciliation

## Overview

The **WIP Exception Engine** is a production-grade, event-driven telemetry system designed to track execution delivery workloads and proactively isolate "Phantom Drift" (inventory missing between delivery cages, backroom staging, and the shop floor). By analyzing physical replenishment events against manifest data, this engine flags stock discrepancies in real-time, empowering retail shift leaders to take immediate resolution actions before shrinkage occurs.

## Architecture

This repository has been comprehensively refactored into a decoupled, event-driven architecture:

1. **Backend State Engine (FastAPI & Pydantic):** 
   - A robust HTTP API powered by FastAPI that maintains the system state via a dedicated telemetry engine (`services/engine.py`).
   - Domain rules, mathematical variance calculations, and financial shrink tracking are strictly modeled using Pydantic schemas.
2. **Frontend Client (Streamlit):**
   - A stateless frontend dashboard (`dashboard.py`) that acts purely as a UI client.
   - It fetches real-time telemetry from the backend and triggers resolution events via API POST requests, cleanly decoupling the visual layer from the business logic.

## Core Features

- **Execution Telemetry:** Monitor real-time progress across physical containers (Delivery Cages, Flattops) as stock transitions through various zones (Backroom Staging, Shop Floor).
- **Phantom Drift Detection:** Automatically flag when expected inventory quantities diverge from physical execution (e.g., Computer Vision fill events and recorded backstock), isolating potential shrinkage immediately.
- **Financial Shrink Tracking:** Dynamically calculate the monetary impact of unresolved phantom drift in real-time based on specific SKU values.
- **3-Way Interactive Resolution:** Shift leaders can address edge tasks directly from the dashboard by confirming stock as "All Found" (backstock), "Not Present" (confirming shrink), or "Partial Found" (split resolution).

## Running Locally

To run the decoupled architecture locally, you will need to start both the backend API and the frontend dashboard in separate terminal instances.

### 1. Start the FastAPI Backend
Ensure your virtual environment is active and dependencies are installed, then run the FastAPI server:

```bash
python3 -m fastapi dev main.py
```
*(The API will be available at `http://localhost:8000`. You can view the Swagger UI documentation at `http://localhost:8000/docs`)*

### 2. Start the Streamlit Frontend
In a new terminal window, start the Streamlit client:

```bash
python3 -m streamlit run dashboard.py
```
*(The dashboard will automatically open in your browser, connecting to the local API backend).*