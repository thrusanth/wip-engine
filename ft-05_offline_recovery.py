#!/usr/bin/env python3
"""
FT-05: Offline edge buffer recovery — pasta case fill (12 units).

Simulates a frontline store task buffered locally during outage, then replays
pending rows through edge_recovery.flush_pending_events() against the Dockerized API.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import List

# Configure edge modules before import (isolated DB for repeatable runs).
os.environ.setdefault("EDGE_BUFFER_PATH", "edge_buffer_ft05.db")
os.environ.setdefault("CENTRAL_LEDGER_URL", "http://127.0.0.1:8000/api/v1/telemetry/fill")
os.environ.setdefault("API_HOST", "127.0.0.1")
os.environ.setdefault("API_PORT", "8000")

import requests

from edge_database import DB_PATH, ensure_edge_buffer
from edge_recovery import BACKEND_URL, flush_pending_events

BACKEND_ORIGIN = os.getenv("FT05_BACKEND_ORIGIN", "http://localhost:8000")

PASTA_SKU = "PASTA-CASE-12"
PASTA_NAME = "Pasta Case"
FILL_QUANTITY = 12
FILL_ACTION = "fill"
EVENT_ID_PREFIX = "TRX-FT05"


def preflight_backend_health() -> None:
    """Verify the Dockerized backend is reachable before sync."""
    paths = ("/health", "/")
    last_error: Exception | None = None
    for path in paths:
        url = f"{BACKEND_ORIGIN.rstrip('/')}{path}"
        try:
            response = requests.get(url, timeout=3.0)
            if response.status_code == 200:
                print(f"Pre-flight OK: {url} -> HTTP {response.status_code}")
                return
            print(f"Pre-flight: {url} -> HTTP {response.status_code}")
        except requests.RequestException as exc:
            last_error = exc
            print(f"Pre-flight failed for {url}: {exc}")

    raise RuntimeError(
        f"Backend not healthy at {BACKEND_ORIGIN} (/health and /). "
        f"Start stack with: docker compose up --build -d"
    ) from last_error


def seed_offline_pasta_fill() -> List[str]:
    """Ensure event_queue exists and insert pending offline fill units."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = ensure_edge_buffer(DB_PATH)
    timestamp = datetime.now(timezone.utc).isoformat()
    event_ids: List[str] = []

    for unit in range(1, FILL_QUANTITY + 1):
        event_id = f"{EVENT_ID_PREFIX}-{uuid.uuid4().hex[:8].upper()}-{unit:02d}"
        event_ids.append(event_id)
        conn.execute(
            """
            INSERT INTO event_queue (event_id, sku, action, timestamp, status)
            VALUES (?, ?, ?, ?, 'pending');
            """,
            (event_id, PASTA_SKU, FILL_ACTION, timestamp),
        )

    conn.close()
    print(
        f"Seeded offline task: {PASTA_NAME} ({PASTA_SKU}) x{FILL_QUANTITY} "
        f"action={FILL_ACTION!r} -> {len(event_ids)} pending row(s) in {DB_PATH}"
    )
    return event_ids


def run_recovery_with_http_tracking() -> List[int]:
    """Run recovery sync and capture HTTP status codes for each POST."""
    status_codes: List[int] = []
    original_post = requests.post

    def tracking_post(*args, **kwargs):
        response = original_post(*args, **kwargs)
        status_codes.append(response.status_code)
        return response

    requests.post = tracking_post  # type: ignore[method-assign]
    try:
        flush_pending_events()
    finally:
        requests.post = original_post  # type: ignore[method-assign]

    return status_codes


def assert_queue_synced(event_ids: List[str]) -> None:
    conn = ensure_edge_buffer(DB_PATH)
    try:
        rows = conn.execute(
            f"""
            SELECT event_id, status
            FROM event_queue
            WHERE event_id IN ({",".join("?" * len(event_ids))});
            """,
            event_ids,
        ).fetchall()

        if len(rows) != len(event_ids):
            raise AssertionError(
                f"Expected {len(event_ids)} queue rows, found {len(rows)}"
            )

        not_synced = [event_id for event_id, status in rows if status != "synced"]
        if not_synced:
            raise AssertionError(
                f"Events not marked synced: {not_synced}"
            )

        pending_left = conn.execute(
            "SELECT COUNT(*) FROM event_queue WHERE status = 'pending';"
        ).fetchone()[0]
    finally:
        conn.close()

    pending_left = int(pending_left)
    if pending_left:
        raise AssertionError(f"Unexpected pending rows remaining: {pending_left}")


def main() -> int:
    print("=== FT-05 Offline Edge Buffer Recovery (Pasta Case Fill) ===")
    print(f"Central ledger URL: {BACKEND_URL}")

    event_ids = seed_offline_pasta_fill()
    preflight_backend_health()

    status_codes = run_recovery_with_http_tracking()
    if not status_codes:
        raise AssertionError(
            "Recovery did not POST any events; queue may be empty or sync aborted early"
        )

    if not all(code == 200 for code in status_codes):
        raise AssertionError(
            f"Expected all sync POSTs to return HTTP 200, got: {status_codes}"
        )

    assert_queue_synced(event_ids)
    print(
        f"PASS: {len(status_codes)} fill event(s) synced with HTTP 200; "
        f"local queue marked synced for {PASTA_SKU} ({PASTA_NAME})."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
