# WIP Exception Engine: Inventory Reconciliation

## Overview

The **WIP Exception Engine** is a production-grade, event-driven telemetry system designed to track execution delivery workloads and proactively isolate "Phantom Drift" (inventory missing between delivery cages, backroom staging, and the shop floor). By analyzing physical replenishment events against manifest data, this engine flags stock discrepancies in real-time, empowering retail shift leaders to take immediate resolution actions before shrinkage occurs.

## Tech Stack

This repository utilizes a decoupled, dockerized architecture for seamless local development and production deployment:

- **Backend:** FastAPI & Uvicorn (Robust, high-performance API server with strict Pydantic data validation).
- **Frontend:** Streamlit (Stateless, reactive UI client for real-time dashboarding).
- **Orchestration:** Docker & Docker Compose (Containerized multi-service deployment).

## Architecture & Networking

The system state is maintained entirely within the backend API engine (`services/engine.py`). The Streamlit dashboard acts purely as a dumb frontend client, fetching telemetry and triggering resolution events via HTTP POST requests. 

The two containers are orchestrated via `docker-compose.yml` on a custom bridge network (`wip-engine-net`). The frontend routes its API requests directly through the host gateway interface to reliably resolve and communicate with the backend service.

## Core Features

- **Execution Telemetry:** Monitor real-time progress across physical containers (Delivery Cages, Flattops) as stock transitions through various zones (Backroom Staging, Shop Floor).
- **Phantom Drift Detection:** Automatically flag when expected inventory quantities diverge from physical execution (e.g., Computer Vision fill events and recorded backstock), isolating potential shrinkage immediately.
- **Financial Shrink Tracking:** Dynamically calculate the monetary impact of unresolved phantom drift in real-time based on specific SKU values.
- **3-Way Interactive Resolution:** Shift leaders can address edge tasks directly from the dashboard by confirming stock as "All Found" (backstock), "Not Present" (confirming shrink), or "Partial Found" (split resolution).

## Getting Started

To run the full decoupled architecture locally using Docker Compose:
## Getting Started

To run the full decoupled architecture locally using Docker Compose:

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/thrusanth/wip_engine.git](https://github.com/thrusanth/wip_engine.git)
   cd wip_engine

### 2. Start the Stack

Clone the repository and spin up the containers in detached mode:

```bash
docker compose up --build -d
```

### 2. Access the Application

Once the containers are built and running, you can access the services in your browser:

- **Streamlit Dashboard (Frontend):** [http://localhost:8501](http://localhost:8501)
- **FastAPI Interactive Docs (Backend):** [http://localhost:8000/docs](http://localhost:8000/docs)
