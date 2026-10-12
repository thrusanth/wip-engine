"""
Multi-product edge CV traffic generator (migrated from api_bouncer/simulator.py).

Targets the integrated WIP Exception Engine middleware on the unified FastAPI backend.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import requests

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = os.getenv("API_PORT", "8000")
WEBHOOK_PATH = os.getenv(
    "BOUNCER_CV_WEBHOOK_PATH",
    "/api/v1/bouncer/cv-detection",
)
WEBHOOK_URL = os.getenv(
    "BOUNCER_CV_WEBHOOK_URL",
    f"http://{API_HOST}:{API_PORT}{WEBHOOK_PATH}",
)

HEADERS = {
    "X-API-Key": os.getenv("BOUNCER_EDGE_TOKEN", "edge-cam-prod-992-xtz"),
    "Content-Type": "application/json",
}

scenarios = [
    {
        "name": "1. Water 6PK: Perfect Shelf Fill (Clean Sync)",
        "payload": {
            "store_region": "ENG",
            "parent_sku": "SKU-WATER-6PK",
            "detected_quantity": 20,
            "physical_location": "Aisle-4-Bay-2",
            "detected_format": "SHRINK_WRAPPED_MULTIPACK",
            "loose_units_visible": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence_score": 0.99,
        },
    },
    {
        "name": "2. Water 6PK in England (£3.00 retail -> £3.00 ÷ 6 = £0.50 per unit)",
        "payload": {
            "store_region": "ENG",
            "parent_sku": "SKU-WATER-6PK",
            "detected_quantity": 19,
            "physical_location": "Aisle-4-Bay-2",
            "detected_format": "TORN_MULTIPACK",
            "loose_units_visible": 3,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence_score": 0.99,
        },
    },
    {
        "name": "3. Baked Beans 4PK in England (£2.40 retail -> £2.40 ÷ 4 = £0.60 per unit)",
        "payload": {
            "store_region": "ENG",
            "parent_sku": "SKU-BEANS-4PK",
            "detected_quantity": 29,
            "physical_location": "Aisle-2-Bay-4",
            "detected_format": "TORN_MULTIPACK",
            "loose_units_visible": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence_score": 0.97,
        },
    },
    {
        "name": "4. Lager 4PK in England (£6.00 retail -> £6.00 ÷ 4 = £1.50 vs Duty+VAT floor)",
        "payload": {
            "store_region": "ENG",
            "parent_sku": "SKU-LAGER-4PK",
            "detected_quantity": 14,
            "physical_location": "Aisle-4-Bay-1",
            "detected_format": "TORN_MULTIPACK",
            "loose_units_visible": 2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence_score": 0.98,
        },
    },
    {
        "name": "5. Cider 4PK in Scotland (£4.00 retail -> £4.00 ÷ 4 = £1.00 overridden by MUP floor)",
        "payload": {
            "store_region": "SCO",
            "parent_sku": "SKU-CIDER-4PK",
            "detected_quantity": 10,
            "physical_location": "Aisle-4-Bay-3",
            "detected_format": "TORN_MULTIPACK",
            "loose_units_visible": 3,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence_score": 0.97,
        },
    },
    {
        "name": "6. Beer 10PK in Wales (£11.00 retail -> £11.00 ÷ 10 = £1.10 overridden by MUP floor)",
        "payload": {
            "store_region": "WAL",
            "parent_sku": "SKU-BEER-10PK",
            "detected_quantity": 8,
            "physical_location": "Aisle-4-Bay-4",
            "detected_format": "TORN_MULTIPACK",
            "loose_units_visible": 6,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence_score": 0.99,
        },
    },
]


def main() -> None:
    print(f"Starting CV traffic simulation against {WEBHOOK_URL}\n")
    for idx, scenario in enumerate(scenarios):
        print(f"[{idx + 1}/{len(scenarios)}] Transmitting: {scenario['name']}")
        response = requests.post(WEBHOOK_URL, json=scenario["payload"], headers=HEADERS, timeout=10)

        if response.status_code == 200:
            res_data = response.json()
            print(f" -> Success! Trace ID: {res_data.get('trace_id')}")
            label_task = res_data.get("label_print_task")
            if label_task:
                print(
                    f"    PDA Print Task Dispatched: {label_task['price_override_instruction']}"
                )
            else:
                print("    Clean Sync Verified (No action required)")
        else:
            print(f" -> Failed! Status: {response.status_code} | Detail: {response.text}")

        time.sleep(2)

    dashboard_base = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}/api/v1").rstrip("/")
    print(
        "\nSimulation complete! View bouncer telemetry in Streamlit (API Bouncer tab) "
        f"or GET {dashboard_base}/bouncer/reconciliations"
    )


if __name__ == "__main__":
    main()
