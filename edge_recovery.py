import os
import time

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


def flush_pending_events() -> None:
    conn = ensure_edge_buffer(DB_PATH)
    cursor = conn.execute(
        """
        SELECT event_id, sku, action, timestamp
        FROM event_queue
        WHERE status = 'pending';
        """
    )
    pending = cursor.fetchall()

    if not pending:
        conn.close()
        return

    print(f"Recovery: found {len(pending)} pending event(s) to sync.")

    for event_id, sku, action, timestamp in pending:
        payload = {
            "event_id": event_id,
            "sku": sku,
            "action": action,
            "timestamp": timestamp,
        }

        try:
            response = requests.post(BACKEND_URL, json=payload, timeout=2.0)
            response.raise_for_status()
            conn.execute(
                "UPDATE event_queue SET status = 'synced' WHERE event_id = ?;",
                (event_id,),
            )
            print(f"Successfully synced event {event_id} to central ledger.")
        except requests.exceptions.RequestException as e:
            print(
                f'Sync failed: {e} - Response: {getattr(e.response, "text", "no response")}'
            )
            break

    conn.close()


if __name__ == "__main__":
    ensure_edge_buffer()
    print("Starting Edge Recovery Worker. Press Ctrl+C to stop.")
    try:
        while True:
            flush_pending_events()
            time.sleep(5)
    except KeyboardInterrupt:
        print("Edge Recovery Worker stopped.")
