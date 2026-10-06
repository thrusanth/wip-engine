import sqlite3
import time

import requests

DB_PATH = "edge_buffer.db"
BACKEND_URL = "http://127.0.0.1:8000/api/v1/telemetry/fill"


def flush_pending_events() -> None:
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
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
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            print("Network still unreachable — pausing flush until next poll cycle.")
            break

    conn.close()


if __name__ == "__main__":
    print("Starting Edge Recovery Worker. Press Ctrl+C to stop.")
    try:
        while True:
            flush_pending_events()
            time.sleep(5)
    except KeyboardInterrupt:
        print("Edge Recovery Worker stopped.")
