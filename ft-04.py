#!/usr/bin/env python3
"""
FT-04: Total Power Cut disaster recovery during inbound delivery.

Uses isolated SKUs (WATER-CASE-24, CEREAL-CASE-10) so FT-03 pasta/rice scenarios stay independent.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import requests

from models.schemas import TOTAL_POWER_CUT_STATUS

BACKEND_ORIGIN = os.getenv("FT04_BACKEND_ORIGIN", "http://localhost:8000")
EVENTS_URL = f"{BACKEND_ORIGIN.rstrip('/')}/api/v1/events"

MANIFEST_ID = "FT-04-DELIVERY-CAGE"

MANIFEST_LINES = [
    {"sku": "WATER-CASE-24", "expected_units": 24},
    {"sku": "CEREAL-CASE-10", "expected_units": 10},
]


def _heading(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def preflight_backend_health() -> None:
    for path in ("/health", "/"):
        url = f"{BACKEND_ORIGIN.rstrip('/')}{path}"
        try:
            response = requests.get(url, timeout=3.0)
            if response.status_code == 200:
                print(f"Pre-flight OK: {url} -> HTTP {response.status_code}")
                return
        except requests.RequestException:
            continue
    raise RuntimeError(
        f"Backend not reachable at {BACKEND_ORIGIN}. Run: docker compose up --build -d"
    )


def main() -> int:
    _heading("FT-04 Total Power Cut — Disaster Recovery")
    preflight_backend_health()

    manifest_payload = {
        "manifest_id": MANIFEST_ID,
        "zone": "Backroom Staging / Bay 3",
        "lines": MANIFEST_LINES,
    }
    stage_response = requests.post(
        f"{EVENTS_URL}/delivery-manifest", json=manifest_payload, timeout=3.0
    )
    if stage_response.status_code != 200:
        raise AssertionError(
            f"Manifest staging failed HTTP {stage_response.status_code}: {stage_response.text}"
        )
    print(f"Staged delivery manifest {MANIFEST_ID} with {len(MANIFEST_LINES)} SKU line(s).")

    power_cut_payload = {
        "manifest_id": MANIFEST_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    cut_response = requests.post(
        f"{EVENTS_URL}/total-power-cut", json=power_cut_payload, timeout=3.0
    )
    if cut_response.status_code != 200:
        raise AssertionError(
            f"Total power cut failed HTTP {cut_response.status_code}: {cut_response.text}"
        )

    telemetry = cut_response.json()
    ledger = telemetry.get("manifest_auto_confirm_audit", [])
    manifest_rows = [row for row in ledger if row.get("manifest_id") == MANIFEST_ID]
    if len(manifest_rows) != len(MANIFEST_LINES):
        raise AssertionError(
            f"Expected {len(MANIFEST_LINES)} ledger rows, found {len(manifest_rows)}"
        )

    for expected in MANIFEST_LINES:
        sku = expected["sku"]
        row = next((item for item in manifest_rows if item.get("sku") == sku), None)
        if row is None:
            raise AssertionError(f"Ledger missing auto-confirm row for {sku}")
        if row.get("confirmed_units") != expected["expected_units"]:
            raise AssertionError(
                f"{sku}: confirmed {row.get('confirmed_units')} != "
                f"expected {expected['expected_units']}"
            )
        if row.get("expected_units") != expected["expected_units"]:
            raise AssertionError(f"{sku}: ledger expected_units mismatch")

    exceptions = telemetry.get("active_exceptions", [])
    power_cut_exceptions = [
        exc
        for exc in exceptions
        if exc.get("kind") == "total_power_cut"
        and exc.get("sku") in {line["sku"] for line in MANIFEST_LINES}
        and exc.get("status") == TOTAL_POWER_CUT_STATUS
    ]
    if len(power_cut_exceptions) != len(MANIFEST_LINES):
        raise AssertionError(
            f"Expected {len(MANIFEST_LINES)} power-cut exceptions, "
            f"found {len(power_cut_exceptions)}"
        )

    containers = telemetry.get("containers", {})
    container = containers.get(MANIFEST_ID)
    if not container:
        raise AssertionError(f"Manifest container {MANIFEST_ID} missing from ledger")

    for expected in MANIFEST_LINES:
        sku = expected["sku"]
        sku_row = next((s for s in container.get("skus", []) if s.get("sku") == sku), None)
        if sku_row is None:
            raise AssertionError(f"Container ledger missing SKU {sku}")
        if sku_row.get("backstock") != expected["expected_units"]:
            raise AssertionError(
                f"{sku}: backstock {sku_row.get('backstock')} != "
                f"expected arrival {expected['expected_units']}"
            )

    print(
        f"PASS: Manifest {MANIFEST_ID} auto-confirmed for all SKUs; "
        f"mandatory gap scan exceptions raised ({len(power_cut_exceptions)})."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
