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

from pathlib import Path

_FT05_ROOT = Path(__file__).resolve().parent
os.environ.setdefault(
    "LOCAL_SKU_WEIGHTS_PATH", str(_FT05_ROOT / "local_sku_weights_ft05.json")
)
os.environ.setdefault(
    "TELEMETRY_BUFFER_PATH", str(_FT05_ROOT / "offline_detection_buffer_ft05.db")
)

from models.schemas import OfflineDetectionEvent
from services.edge_learning import EdgeInferenceEngine
from services.telemetry_sync import TelemetryBuffer

SKU_ID = "ENERGY-DRINK-12PK"
SKU_EAN = "5012345678908"
MOCK_IMAGE_DATA = b"ft05-mock-shelf-scan-energy-drink-12pk-layout-v1"
DISCONNECTED_STATUS = "[STATE: DISCONNECTED_AUTONOMY]"

WEIGHTS_PATH = os.environ["LOCAL_SKU_WEIGHTS_PATH"]
BUFFER_PATH = os.environ["TELEMETRY_BUFFER_PATH"]


def _step(label: str) -> None:
    print()
    print(f"--- {label} ---")


def _detail(message: str) -> None:
    print(f"    {message}")


def _reset_local_artifacts() -> None:
    """Remove FT-05 JSON/SQLite artifacts (and SQLite WAL sidecars) for a clean run."""
    targets = (
        "local_sku_weights_ft05.json",
        "offline_detection_buffer_ft05.db",
        "offline_detection_buffer_ft05.db-wal",
        "offline_detection_buffer_ft05.db-shm",
    )
    for name in targets:
        path = _FT05_ROOT / name
        if path.is_file():
            path.unlink()
            print(f"Removed existing artifact: {path.name}")


async def run_edge_autonomy_lifecycle() -> None:
    _step("1/6 Script start")
    print("FT-05 Localized Edge Autonomy — execution log")
    print("Initializing EdgeInferenceEngine …")
    engine = EdgeInferenceEngine(WEIGHTS_PATH)
    print(f"EdgeInferenceEngine ready (weights cache: {WEIGHTS_PATH}).")

    _step("2/6 Cloud teaching (online)")
    print(f"Calling teach_edge_from_cloud(sku_id={SKU_ID!r}, ean={SKU_EAN!r}) …")
    signature = await engine.teach_edge_from_cloud(
        SKU_ID, MOCK_IMAGE_DATA, ean=SKU_EAN
    )
    if signature.sku_id != SKU_ID or not signature.feature_hash:
        raise AssertionError("Cloud teach did not persist a valid visual signature")
    if signature.ean != SKU_EAN:
        raise AssertionError(f"Expected EAN {SKU_EAN!r}, got {signature.ean!r}")
    print("teach_edge_from_cloud() complete.")
    print(f"feature_hash: {signature.feature_hash}")
    print(f"ean: {signature.ean}")

    _step("3/6 Simulated network blackout")
    print("WARNING: Store network dropped — entering simulated blackout.")
    print(f"WARNING: Edge camera state -> {DISCONNECTED_STATUS}")

    _step("4/6 Autonomous offline inference")
    print("Calling autonomous_offline_inference() with taught shelf frame …")
    recognition = await engine.autonomous_offline_inference(MOCK_IMAGE_DATA)
    if recognition is None:
        raise AssertionError("Offline inference failed to match taught feature hash")
    if recognition.sku_id != SKU_ID:
        raise AssertionError(
            f"Expected SKU {SKU_ID}, got {recognition.sku_id} from local cache"
        )
    print("autonomous_offline_inference() matched local signature (no cloud required).")
    _detail(f"sku_id: {recognition.sku_id}")
    _detail(f"feature_hash: {recognition.feature_hash}")

    _step("5/6 SQLite WAL buffer write")
    telemetry_buffer = TelemetryBuffer(BUFFER_PATH)
    offline_event = OfflineDetectionEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        sku_id=recognition.sku_id,
        detected_quantity=1,
    )
    if offline_event.status != DISCONNECTED_STATUS:
        raise AssertionError("OfflineDetectionEvent default status mismatch")
    _detail(f"buffer: {BUFFER_PATH}")
    _detail(f"event sku_id={offline_event.sku_id}, qty={offline_event.detected_quantity}")
    telemetry_buffer.log_offline_detection(offline_event)
    print("Offline detection event written to SQLite WAL buffer (offline_detection_log).")

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
    if logged_sku != SKU_ID or logged_qty != 1 or logged_status != DISCONNECTED_STATUS:
        raise AssertionError(f"WAL read-back mismatch: {row!r}")

    _step("6/6 Final success summary")
    print("FT-05 PASSED — all stages verified:")
    _detail("Cloud teach persisted visual signature to local JSON cache")
    _detail("Blackout autonomy recognized SKU via local hash lookup")
    _detail(f"WAL row read back: sku={logged_sku}, status={logged_status}")


def main() -> int:
    asyncio.run(run_edge_autonomy_lifecycle())
    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    print("FT-05: starting from a clean slate (removing prior FT-05 cache/buffer files if present).")
    _reset_local_artifacts()
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
