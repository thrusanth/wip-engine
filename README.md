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

The two containers are orchestrated via `docker-compose.yml` on a custom bridge network (`wip-engine-net`). The Streamlit frontend resolves the FastAPI backend by Docker service hostname (`http://backend:8000/api/v1`) with no host port conflicts on the internal bridge.

## API Bouncer (Integrated Edge Ingress Middleware)

The **API Bouncer** layer (merged from the standalone `api_bouncer` project) sits in front of protected ingress routes inside the unified FastAPI backend. It intercepts edge camera webhooks and telemetry fill payloads **before** they are persisted to the SQLite WAL audit buffer or applied to the central execution engine.

### Architectural Role

- **Middleware (`middleware/api_bouncer.py`):** Enforces per-client rate limits, JSON integrity checks, payload size caps, and edge token authentication on:
  - `POST /api/v1/bouncer/cv-detection` (primary CV webhook)
  - `POST /webhook/cv-detection` (legacy simulator compatibility)
  - `POST /api/v1/telemetry/fill` (edge fill telemetry destined for engine + offline audit)
- **Reconciliation engine (`services/api_bouncer_engine.py`):** Validates CV confidence (≥ 0.80 for INTACT stock, ≥ 0.70 for damage detections), compares detected shelf formats against the central ledger, performs BOM decomposition for torn multipacks, and applies UK alcohol pricing floors (England Duty+VAT vs Scotland/Wales MUP).
- **WAL audit buffer (`services/bouncer_buffer.py`):** Stores reconciliation outcomes and active API rejections in `bouncer_audit.db` (configurable via `BOUNCER_BUFFER_PATH`).

### Rate Limiting & Security Rules

| Route | Auth | Default throttle | Integrity gates |
| --- | --- | --- | --- |
| CV detection webhooks | `X-API-Key: BOUNCER_EDGE_TOKEN` | 30 requests / minute / client IP | Required CV fields, confidence range, JSON ≤ 64 KiB |
| Telemetry fill | Open (shop-floor edge clients) | 120 requests / minute / client IP | Required fill fields (`event_id`, `sku`, `action`, `timestamp`) |

Rejected requests receive HTTP `401`, `413`, `415`, `422`, or `429` responses and are appended to the bouncer rejection log for the Streamlit **API Bouncer** tab.

### Bouncer Setup & Simulation

Environment variables (see `.env.example`):

- `BOUNCER_EDGE_TOKEN` — edge camera ingress token (default `edge-cam-prod-992-xtz`); set on **both** backend and Streamlit for manual shopfloor injects
- `BOUNCER_ALLOW_DEMO_EDGE_TOKEN` — when `true` (default), also accepts the public demo token so dashboard injects work without matching a rotated secret; set `false` in hardened production
- `BOUNCER_CV_RATE_LIMIT_PER_MINUTE`, `BOUNCER_FILL_RATE_LIMIT_PER_MINUTE`, `BOUNCER_MAX_BODY_BYTES`
- `BOUNCER_BUFFER_PATH` — SQLite WAL path for audit + rejection logs

Run integrated traffic simulation against the merged middleware:

```bash
# With Docker Compose stack running
python3 tests/simulate_cv_traffic.py
```

Inspect live health, rejections, and throttle limits in the Streamlit dashboard (**API Bouncer** tab) or via:

- `GET /api/v1/bouncer/health`
- `GET /api/v1/bouncer/rejections`
- `GET /api/v1/bouncer/reconciliations`

## Core Features

- **Execution Telemetry:** Monitor real-time progress across physical containers (Delivery Cages, Flattops) as stock transitions through various zones (Backroom Staging, Shop Floor).
- **Phantom Drift Detection:** Automatically flag when expected inventory quantities diverge from physical execution (e.g., Computer Vision fill events and recorded backstock), isolating potential shrinkage immediately.
- **Financial Shrink Tracking:** Dynamically calculate the monetary impact of unresolved phantom drift in real-time based on specific SKU values.
- **3-Way Interactive Resolution:** Shift leaders can address edge tasks directly from the dashboard by confirming stock as "All Found" (backstock), "Not Present" (confirming shrink), or "Partial Found" (split resolution).
- **Edge Blackout Autonomy & Disaster Recovery (Part 5):** Offline SQLite WAL buffering for network-disconnected restock fills (`ft-03`), local hash-based edge computer vision fingerprinting (`ft-05`), and catastrophic power loss disaster recovery protocols enforcing mandatory post-blackout gap scans (`ft-04`).

## Getting Started

To run the full decoupled architecture locally using Docker Compose:

1. **Clone and checkout the branch:**
   ```bash
   git clone https://github.com/thrusanth/wip-engine.git
   cd wip-engine

### 2. Start the Stack

Clone the repository and spin up the containers in detached mode:

```bash
docker compose up --build -d
```

### 3. Access the Application

Once the containers are built and running, you can access the services in your browser:

- **Streamlit Dashboard (Frontend):** [http://localhost:8501](http://localhost:8501)
- **FastAPI Interactive Docs (Backend):** [http://localhost:8000/docs](http://localhost:8000/docs)

### Running Blackout & Edge Resilience Simulations

To test the offline edge buffer, camera autonomy, and power cut disaster recovery scripts locally against the containerized backend:

```bash
# Ensure your Docker Compose stack is running
docker compose up -d

# Run the master functional test suite:
python3 ft-03.py  # Network drop, offline fill telemetry, & asynchronous SQLite WAL recovery
python3 ft-04.py  # Catastrophic total power cut disaster recovery & mandatory store gap scans
python3 ft-05.py  # Localized edge AI computer vision autonomy & local hash fingerprinting
python3 tests/simulate_cv_traffic.py  # API Bouncer CV webhook & compliance simulation
```
