# WIP Exception Engine — *The Inventory Phantoms* (Part 5)

## Project Overview

The **WIP Exception Engine** is an event-driven retail telemetry system that tracks delivery-cage and flattop execution, surfaces **phantom drift** (inventory that disappears between manifest, backroom, and shelf), and gives shift leaders tools to reconcile shrink before it compounds.

**Part 5** extends the engine for **network disruption and edge resilience**:

| Capability | What it does |
|------------|----------------|
| **Network drop & offline buffer** | Fill telemetry fails fast to a local **SQLite WAL** queue (`edge_database.py`, `edge_interceptor.py`, `edge_recovery.py`) and replays to the central ledger when connectivity returns. |
| **Offline fill & gap audit** | Partial offline fills flag **gap scan** exceptions and ledger rows (validated by **FT-03**). |
| **Localized Edge AI autonomy** | Cloud “teach” passes store **SHA-256 visual fingerprints** in JSON; blackouts use **O(1) hash lookup** on-device (`services/edge_learning.py`, `services/telemetry_sync.py`, **FT-05**). |
| **Total power cut disaster recovery** | Pending delivery manifests can be **auto-confirmed** under emergency protocol with **mandatory full gap scan** exceptions quarantined to the dashboard offline tab (**FT-04**). |

The **FastAPI backend** (`services/engine.py`) owns system state. **Streamlit** (`dashboard.py`) is a read/write client for live ops and a read-only view of edge autonomy artifacts on Tab 4.

---

## Prerequisites

- **Docker** and **Docker Compose** (v2 `docker compose` recommended)
- **Python 3.9+** on the host for functional tests (3.10+ preferred)
- Host tools: `git`, `curl` or browser for health checks

For local test scripts only (outside Docker):

```bash
pip install -r requirements.txt
```

FT-05 additionally needs no extra packages beyond the main requirements (uses stdlib + project modules). Optional PDF export: `pip install -r requirements-export.txt`.

---

## Quick Start (Docker)

From the repository root:

```bash
docker compose up --build -d
```

Verify services:

| Service | URL |
|---------|-----|
| **Streamlit dashboard** | [http://localhost:8501](http://localhost:8501) |
| **FastAPI docs** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **Health** | [http://localhost:8000/health](http://localhost:8000/health) |

Stop the stack:

```bash
docker compose down
```

**Notes:**

- Backend listens on **8000**; frontend on **8501**.
- The frontend bind-mounts **`.:/app`** so files written on the host (e.g. by `ft-05.py`) appear immediately in the containerized dashboard.
- Copy `.env.example` to `.env` if you customize API keys or ledger URLs.

---

## Master Functional Tests (Edge Simulations)

Run tests from the **repository root** on the host unless noted. **FT-03** and **FT-04** require the Docker backend (or any reachable instance at `http://localhost:8000`). **FT-05** is self-contained and does not need the API.

### `python3 ft-03.py` — Network drop, offline fills, WAL recovery

**Simulates:** Edge buffer seeding during outage → recovery flush → central ledger **offline fill audit** → partial fill **gap scan** (RICE-CASE-6).

**Flow:**

1. Preflight `GET /health` on the backend.
2. **Scenario 1 (PASTA-CASE-12):** Seeds 12 pending fill rows in `edge_buffer_ft03.db`, runs `flush_pending_events()`, asserts HTTP 200 and `synced` queue state, verifies `offline_fill_audit` on `/api/v1/telemetry`.
3. **Scenario 2 (RICE-CASE-6):** Partial offline fill (4/6), gap report to `/api/v1/telemetry/offline-partial-fill`, asserts `inventory_gap_audit` and **Gap Scan Recommended** in `active_exceptions`.

**Environment (optional overrides):**

- `FT03_BACKEND_ORIGIN` (default `http://localhost:8000`)
- `EDGE_BUFFER_PATH=edge_buffer_ft03.db`
- `CENTRAL_LEDGER_URL=http://127.0.0.1:8000/api/v1/telemetry/fill`

```bash
docker compose up --build -d
python3 ft-03.py
```

---

### `python3 ft-04.py` — Total power cut disaster recovery

**Simulates:** Staging an inbound delivery manifest → **total power cut** mid-breakdown → emergency **auto-confirm** to the central ledger → `TOTAL_POWER_CUT` exceptions with **Mandatory Full Gap Scan Required** (isolated SKUs: `WATER-CASE-24`, `CEREAL-CASE-10`).

**Flow:**

1. `POST /api/v1/events/delivery-manifest`
2. `POST /api/v1/events/total-power-cut`
3. Asserts `manifest_auto_confirm_audit`, container backstock, and power-cut `active_exceptions`.

```bash
docker compose up --build -d
python3 ft-04.py
```

Power-cut data is **quarantined** from Tabs 1–2 on the dashboard; review cards and banner appear under **Tab 3 (Offline Fill)** only.

---

### `python3 ft-05.py` — Edge AI autonomy (teach, blackout, local infer, WAL)

**Simulates:** Six-stage edge CV autonomy without the central API:

1. Clears prior **`local_sku_weights_ft05.json`** and **`offline_detection_buffer_ft05.db`** (+ WAL sidecars).
2. **Online teach** — `EdgeInferenceEngine.teach_edge_from_cloud("ENERGY-DRINK-12PK", …)` writes SHA-256 signature to JSON.
3. **Blackout** — operational state **`[STATE: DISCONNECTED_AUTONOMY]`** (logged).
4. **Autonomous inference** — same frame bytes → local hash match (no cloud).
5. **WAL append** — `TelemetryBuffer.log_offline_detection()` inserts into SQLite.
6. **Read-back** — asserts latest row status and SKU.

```bash
python3 ft-05.py
```

No Docker required for the test itself; run the dashboard container afterward (or keep it running) to inspect Tab 4.

**Legacy:** `ft-05_offline_recovery.py` delegates to FT-03 Scenario 1; prefer `ft-03.py`.

---

## Operator Observability (UI)

Open **[http://localhost:8501](http://localhost:8501)** after `docker compose up -d`.

| Tab | Purpose |
|-----|---------|
| **System Overview / Telemetry & Exceptions** | Live flattop metrics, drift table, execution cards (power-cut manifests **hidden** here). |
| **Tab 3 — Offline Fill** | Post-blackout **offline fill audit**, partial-fill **gap scan** cards, and **Total Power Cut** disaster recovery (red banner + emergency SKU cards) after **FT-03** / **FT-04**. |
| **Tab 4 — Edge AI Autonomy** | Read-only edge CV state: **`[STATE: DISCONNECTED_AUTONOMY]`**, counts and tables for **cached visual signatures** (`local_sku_weights_ft05.json`) and **pending offline scans** (`offline_detection_buffer_ft05.db`) after **FT-05**. |

**Suggested demo sequence:**

```bash
docker compose up --build -d
python3 ft-03.py    # Tab 3: pasta full sync + rice gap (use checkbox for all fills if needed)
python3 ft-04.py    # Tab 3: power cut banner + WATER/CEREAL cards
python3 ft-05.py    # Tab 4: signature count + WAL queue (host files via `.:/app` mount)
```

Refresh the browser between tests if the dashboard does not auto-reload.

---

## Repository map (Part 5 edge stack)

| Path | Role |
|------|------|
| `edge_database.py` | SQLite WAL `event_queue` for fill telemetry |
| `edge_interceptor.py` | 1s timeout POST → local enqueue on failure |
| `edge_recovery.py` | Replay pending queue to central ledger |
| `services/edge_learning.py` | JSON visual signature cache + offline inference |
| `services/telemetry_sync.py` | Append-only offline detection WAL log |
| `services/engine.py` | Central ledger, offline fill/gap/power-cut logic |
| `dashboard.py` | Streamlit UI (Tabs 3–4 for Part 5 observability) |
| `ft-03.py`, `ft-04.py`, `ft-05.py` | Master functional tests |

---

## Tech stack

- **Backend:** FastAPI, Uvicorn, Pydantic  
- **Frontend:** Streamlit  
- **Edge persistence:** SQLite (WAL), JSON signature cache  
- **Orchestration:** Docker Compose  

For deeper architecture notes, see inline docstrings in `services/edge_learning.py` and `services/telemetry_sync.py`.
