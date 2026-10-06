import os
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from edge_database import DB_PATH, ensure_edge_buffer
from routers.telemetry import FILL_ROUTE, router as telemetry_router

load_dotenv()

_default_host = os.getenv("API_HOST", "127.0.0.1")
_default_port = os.getenv("API_PORT", "8000")
_default_central_ledger_url = (
    f"http://{_default_host}:{_default_port}{telemetry_router.prefix}{FILL_ROUTE}"
)
BACKEND_URL = os.getenv("CENTRAL_LEDGER_URL", _default_central_ledger_url)


def emit_fill_event(sku: str, action: str = "decrement") -> None:
    event_id = f"TRX-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = {
        "event_id": event_id,
        "sku": sku,
        "action": action,
        "timestamp": timestamp,
    }

    try:
        response = requests.post(BACKEND_URL, json=payload, timeout=1.0)
        response.raise_for_status()
        print(f"Successfully emitted fill event {event_id} for SKU {sku}.")
    except requests.exceptions.RequestException:
        print(
            f"Network outage detected — caching event {event_id} locally for later sync."
        )
        conn = ensure_edge_buffer(DB_PATH)
        conn.execute(
            """
            INSERT OR IGNORE INTO event_queue (event_id, sku, action, timestamp, status)
            VALUES (?, ?, ?, ?, 'pending');
            """,
            (payload["event_id"], payload["sku"], payload["action"], payload["timestamp"]),
        )
        conn.close()


if __name__ == "__main__":
    ensure_edge_buffer()
    print(
        "Simulation: rapid fill events during network outage (backend may be unreachable)."
    )
    emit_fill_event("BAKED-BEANS-6PK")
    emit_fill_event("BAKED-BEANS-6PK")
    emit_fill_event("BAKED-BEANS-6PK")
