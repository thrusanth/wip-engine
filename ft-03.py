#!/usr/bin/env python3
"""
FT-03: Inventory resilience master functional test.

Scenario 1 — Offline edge buffer recovery (PASTA-CASE-12, 12-unit fill).
Scenario 2 — Backstock discrepancy & gap scan (RICE-CASE-6, 4/6 shelf fill).
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Callable, List

os.environ.setdefault("EDGE_BUFFER_PATH", "edge_buffer_ft03.db")
os.environ.setdefault("CENTRAL_LEDGER_URL", "http://127.0.0.1:8000/api/v1/telemetry/fill")
os.environ.setdefault("API_HOST", "127.0.0.1")
os.environ.setdefault("API_PORT", "8000")

import requests

from edge_database import DB_PATH, ensure_edge_buffer
from edge_recovery import BACKEND_URL, flush_pending_events

BACKEND_ORIGIN = os.getenv("FT03_BACKEND_ORIGIN", "http://localhost:8000")
TELEMETRY_URL = f"{BACKEND_ORIGIN.rstrip('/')}/api/v1/telemetry"
GAP_REPORT_URL = f"{TELEMETRY_URL}/offline-partial-fill"

# --- Scenario 1: Pasta offline recovery ---
PASTA_SKU = "PASTA-CASE-12"
PASTA_NAME = "Pasta Case"
PASTA_QTY = 12
FILL_ACTION = "fill"
PASTA_EVENT_PREFIX = "TRX-FT03-PASTA"

# --- Scenario 2: Rice partial fill / gap scan ---
RICE_SKU = "RICE-CASE-6"
RICE_NAME = "Microwave Rice"
RICE_CASE_SIZE = 6
RICE_RECORDED_SHELF = 4
RICE_UNLOGGED = RICE_CASE_SIZE - RICE_RECORDED_SHELF
RICE_EVENT_PREFIX = "TRX-FT03-RICE"
RICE_GAP_BATCH = "TRX-FT03-RICE-GAP"


def _heading(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _pass(message: str) -> None:
    print(f"PASS: {message}")


def preflight_backend_health() -> None:
    last_error: Exception | None = None
    for path in ("/health", "/"):
        url = f"{BACKEND_ORIGIN.rstrip('/')}{path}"
        try:
            response = requests.get(url, timeout=3.0)
            if response.status_code == 200:
                print(f"Pre-flight OK: {url} -> HTTP {response.status_code}")
                return
        except requests.RequestException as exc:
            last_error = exc
    raise RuntimeError(
        f"Backend not reachable at {BACKEND_ORIGIN}. Run: docker compose up --build -d"
    ) from last_error


def reset_edge_buffer() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    ensure_edge_buffer(DB_PATH)


def seed_pending_fills(
    *,
    sku: str,
    quantity: int,
    action: str,
    event_prefix: str,
) -> List[str]:
    conn = ensure_edge_buffer(DB_PATH)
    timestamp = datetime.now(timezone.utc).isoformat()
    event_ids: List[str] = []
    for unit in range(1, quantity + 1):
        event_id = f"{event_prefix}-{uuid.uuid4().hex[:8].upper()}-{unit:02d}"
        event_ids.append(event_id)
        conn.execute(
            """
            INSERT INTO event_queue (event_id, sku, action, timestamp, status)
            VALUES (?, ?, ?, ?, 'pending');
            """,
            (event_id, sku, action, timestamp),
        )
    conn.close()
    return event_ids


def run_recovery_with_http_tracking() -> List[int]:
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
            SELECT event_id, status FROM event_queue
            WHERE event_id IN ({",".join("?" * len(event_ids))});
            """,
            event_ids,
        ).fetchall()
        not_synced = [eid for eid, status in rows if status != "synced"]
        pending = conn.execute(
            "SELECT COUNT(*) FROM event_queue WHERE status = 'pending';"
        ).fetchone()[0]
    finally:
        conn.close()

    if len(rows) != len(event_ids):
        raise AssertionError(f"Expected {len(event_ids)} queue rows, found {len(rows)}")
    if not_synced:
        raise AssertionError(f"Events not marked synced: {not_synced}")
    if pending:
        raise AssertionError(f"Unexpected pending rows remaining: {pending}")


def fetch_telemetry() -> dict:
    response = requests.get(TELEMETRY_URL, timeout=3.0)
    response.raise_for_status()
    return response.json()


def scenario_01_offline_edge_recovery() -> None:
    _heading("SCENARIO 1 — Offline Edge Recovery (PASTA-CASE-12)")
    print(f"Central ledger URL: {BACKEND_URL}")

    reset_edge_buffer()
    event_ids = seed_pending_fills(
        sku=PASTA_SKU,
        quantity=PASTA_QTY,
        action=FILL_ACTION,
        event_prefix=PASTA_EVENT_PREFIX,
    )
    print(
        f"Seeded offline task: {PASTA_NAME} ({PASTA_SKU}) x{PASTA_QTY} "
        f"action={FILL_ACTION!r} -> {len(event_ids)} pending row(s)"
    )

    status_codes = run_recovery_with_http_tracking()
    if not status_codes or not all(code == 200 for code in status_codes):
        raise AssertionError(f"Expected all sync POSTs HTTP 200, got: {status_codes}")

    assert_queue_synced(event_ids)

    audit = fetch_telemetry().get("offline_fill_audit", [])
    pasta_rows = [row for row in audit if row.get("sku") == PASTA_SKU]
    if len(pasta_rows) < PASTA_QTY:
        raise AssertionError(
            f"Central ledger expected >={PASTA_QTY} pasta audit rows, found {len(pasta_rows)}"
        )

    _pass(
        f"{len(status_codes)} offline fill(s) synced (HTTP 200); "
        f"SQLite queue synced for {PASTA_SKU} ({PASTA_NAME})."
    )


def scenario_02_backstock_gap_scan() -> None:
    _heading("SCENARIO 2 — Backstock Discrepancy & Gap Scan (RICE-CASE-6)")

    reset_edge_buffer()
    event_ids = seed_pending_fills(
        sku=RICE_SKU,
        quantity=RICE_RECORDED_SHELF,
        action=FILL_ACTION,
        event_prefix=RICE_EVENT_PREFIX,
    )
    print(
        f"Simulated offline partial fill: {RICE_NAME} ({RICE_SKU}) — "
        f"{RICE_RECORDED_SHELF}/{RICE_CASE_SIZE} units to shelf"
    )

    status_codes = run_recovery_with_http_tracking()
    if not status_codes or not all(code == 200 for code in status_codes):
        raise AssertionError(f"Rice shelf sync failed, status codes: {status_codes}")
    assert_queue_synced(event_ids)

    variance_delta = RICE_RECORDED_SHELF - RICE_CASE_SIZE
    print(
        f"Variance: Expected={RICE_CASE_SIZE}, Recorded={RICE_RECORDED_SHELF}, "
        f"Delta={variance_delta} units"
    )
    assert variance_delta == -RICE_UNLOGGED

    gap_payload = {
        "batch_id": RICE_GAP_BATCH,
        "sku": RICE_SKU,
        "expected_units": RICE_CASE_SIZE,
        "recorded_shelf_units": RICE_RECORDED_SHELF,
        "action": FILL_ACTION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    gap_response = requests.post(GAP_REPORT_URL, json=gap_payload, timeout=3.0)
    if gap_response.status_code != 200:
        raise AssertionError(
            f"Gap report failed HTTP {gap_response.status_code}: {gap_response.text}"
        )

    telemetry = gap_response.json()
    gap_audit = telemetry.get("inventory_gap_audit", [])
    rice_gaps = [row for row in gap_audit if row.get("sku") == RICE_SKU]
    if not rice_gaps:
        raise AssertionError("inventory_gap_audit missing RICE-CASE-6 entry")

    gap_row = rice_gaps[-1]
    if gap_row.get("unlogged_backstock_units") != RICE_UNLOGGED:
        raise AssertionError(
            f"Expected {RICE_UNLOGGED} unlogged units, got {gap_row.get('unlogged_backstock_units')}"
        )
    if gap_row.get("status") != "Gap Scan Recommended":
        raise AssertionError(f"Unexpected gap ledger status: {gap_row.get('status')}")

    exceptions = telemetry.get("active_exceptions", [])

    def _is_gap_scan_exception(exc: dict) -> bool:
        if exc.get("sku") != RICE_SKU:
            return False
        if exc.get("status") == "Gap Scan Recommended":
            return True
        message = (exc.get("message") or "").lower()
        return "gap scan recommended" in message

    rice_exceptions = [exc for exc in exceptions if _is_gap_scan_exception(exc)]
    if not rice_exceptions:
        raise AssertionError(
            "Exception feed missing Gap Scan Recommended for RICE-CASE-6 "
            f"(active_exceptions={len(exceptions)})"
        )

    exc = rice_exceptions[-1]
    if exc.get("units") != RICE_UNLOGGED:
        raise AssertionError(f"Exception units expected {RICE_UNLOGGED}, got {exc.get('units')}")

    _pass(
        f"{RICE_RECORDED_SHELF} shelf fills synced; {RICE_UNLOGGED} unlogged backstock flagged "
        f"with Gap Scan Recommended in ledger and exception feed."
    )


def main() -> int:
    _heading("FT-03 Inventory Resilience — Master Functional Test")
    preflight_backend_health()

    scenarios: List[tuple[str, Callable[[], None]]] = [
        ("Offline Edge Recovery", scenario_01_offline_edge_recovery),
        ("Backstock Discrepancy & Gap Scan", scenario_02_backstock_gap_scan),
    ]

    for name, fn in scenarios:
        try:
            fn()
        except Exception as exc:
            print(f"FAIL [{name}]: {exc}", file=sys.stderr)
            return 1

    _heading("FT-03 COMPLETE — ALL SCENARIOS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
