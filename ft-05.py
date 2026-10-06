#!/usr/bin/env python3
"""
FT-05: Localized Edge Autonomy — cloud teach, network blackout, offline inference, WAL tally.

Self-contained functional test (no FastAPI backend required).
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("LOCAL_SKU_WEIGHTS_PATH", "local_sku_weights_ft05.json")
os.environ.setdefault("TELEMETRY_BUFFER_PATH", "offline_detection_buffer_ft05.db")

from models.schemas import OfflineDetectionEvent
from services.edge_learning import EdgeInferenceEngine
from services.telemetry_sync import TelemetryBuffer

SKU_ID = "ENERGY-DRINK-12PK"
MOCK_IMAGE_DATA = b"ft05-mock-shelf-scan-energy-drink-12pk-layout-v1"
DISCONNECTED_STATUS = "[STATE: DISCONNECTED_AUTONOMY]"

WEIGHTS_PATH = os.environ["LOCAL_SKU_WEIGHTS_PATH"]
BUFFER_PATH = os.environ["TELEMETRY_BUFFER_PATH"]


def _heading(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _reset_local_artifacts() -> None:
    for path in (WEIGHTS_PATH, BUFFER_PATH):
        if os.path.exists(path):
            os.remove(path)
    wal = f"{BUFFER_PATH}-wal"
    shm = f"{BUFFER_PATH}-shm"
    for path in (wal, shm):
        if os.path.exists(path):
            os.remove(path)


def _pass(message: str) -> None:
    print(f"PASS: {message}")


async def run_edge_autonomy_lifecycle() -> None:
    _reset_local_artifacts()

    _heading("Phase 1 — Teaching (online cloud → edge cache)")
    engine = EdgeInferenceEngine(WEIGHTS_PATH)
    signature = await engine.teach_edge_from_cloud(SKU_ID, MOCK_IMAGE_DATA)
    if signature.sku_id != SKU_ID or not signature.feature_hash:
        raise AssertionError("Cloud teach did not persist a valid visual signature")
    _pass(f"Edge cache taught for {SKU_ID} (feature_hash={signature.feature_hash[:12]}…)")

    _heading("Phase 2 — Blackout (store network dropped)")
    print(
        "WARNING: Central ledger unreachable — edge camera entering DISCONNECTED_AUTONOMY mode.",
        file=sys.stderr,
    )

    _heading("Phase 3 — Autonomous inference (local JSON cache only)")
    recognition = await engine.autonomous_offline_inference(MOCK_IMAGE_DATA)
    if recognition is None:
        raise AssertionError("Offline inference failed to match taught feature hash")
    if recognition.sku_id != SKU_ID:
        raise AssertionError(
            f"Expected SKU {SKU_ID}, got {recognition.sku_id} from local cache"
        )
    _pass(f"Offline inference recognized {recognition.sku_id} without cloud connectivity")

    _heading("Phase 4 — WAL tally (append offline detection)")
    telemetry_buffer = TelemetryBuffer(BUFFER_PATH)
    offline_event = OfflineDetectionEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        sku_id=recognition.sku_id,
        detected_quantity=1,
    )
    if offline_event.status != DISCONNECTED_STATUS:
        raise AssertionError("OfflineDetectionEvent default status mismatch")
    telemetry_buffer.log_offline_detection(offline_event)

    _heading("Phase 5 — Validation (SQLite offline buffer)")
    row = telemetry_buffer.connect().execute(
        """
        SELECT sku_id, detected_quantity, status
        FROM offline_detection_log
        ORDER BY id DESC
        LIMIT 1;
        """
    ).fetchone()
    telemetry_buffer.close()

    if row is None:
        raise AssertionError("No rows found in offline_detection_log")
    logged_sku, logged_qty, logged_status = row
    if logged_sku != SKU_ID:
        raise AssertionError(f"WAL sku_id mismatch: {logged_sku}")
    if logged_qty != 1:
        raise AssertionError(f"WAL detected_quantity mismatch: {logged_qty}")
    if logged_status != DISCONNECTED_STATUS:
        raise AssertionError(
            f"WAL status expected {DISCONNECTED_STATUS!r}, got {logged_status!r}"
        )
    _pass(f"SQLite WAL row appended with status {DISCONNECTED_STATUS}")


def main() -> int:
    _heading("FT-05 Localized Edge Autonomy")
    asyncio.run(run_edge_autonomy_lifecycle())
    print()
    print("FT-05 completed successfully — edge teach, blackout inference, and WAL tally verified.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
