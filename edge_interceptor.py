import sqlite3
import uuid
from datetime import datetime, timezone

import requests

DB_PATH = "edge_buffer.db"
BACKEND_URL = "http://127.0.0.1:8000/api/v1/telemetry/fill"


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
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        print(
            f"Network outage detected — caching event {event_id} locally for later sync."
        )
        conn = sqlite3.connect(DB_PATH, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute(
            """
            INSERT OR IGNORE INTO event_queue (event_id, sku, action, timestamp, status)
            VALUES (?, ?, ?, ?, 'pending');
            """,
            (payload["event_id"], payload["sku"], payload["action"], payload["timestamp"]),
        )
        conn.close()


if __name__ == "__main__":
    print(
        "Simulation: rapid fill events during network outage (backend may be unreachable)."
    )
    emit_fill_event("BAKED-BEANS-6PK")
    emit_fill_event("BAKED-BEANS-6PK")
    emit_fill_event("BAKED-BEANS-6PK")
