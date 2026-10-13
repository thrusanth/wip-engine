"""Stateless shopfloor scenario transmitter (mirrors tests/simulate_cv_traffic.py networking)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")


def _cv_webhook_url() -> str:
    explicit = os.getenv("BOUNCER_CV_WEBHOOK_URL")
    if explicit:
        return explicit
    return f"{BASE_URL}/bouncer/cv-detection"


def _edge_headers() -> dict[str, str]:
    return {
        "X-API-Key": os.getenv("BOUNCER_EDGE_TOKEN", "edge-cam-prod-992-xtz"),
        "Content-Type": "application/json",
    }


def _detected_format_for_exception(exception_type: str) -> str:
    if exception_type == "TORN_MULTIPACK":
        return "TORN_MULTIPACK"
    return "SHRINK_WRAPPED_MULTIPACK"


def inject_custom_payload(
    *,
    ean: str,
    product_name: str,
    exception_type: str,
    total_units: int,
    damaged_units: int = 0,
    units_lost: int = 0,
    expected_ean: Optional[str] = None,
    fixture_id: str = "CAM-AISLE-04",
) -> tuple[requests.Response, str]:
    """
    Build an edge-camera JSON payload and POST to the API Bouncer CV endpoint.
    Returns (HTTP response, TRX trace id).
    """
    from services.shopfloor_catalog import parent_sku_for_ean

    trx_id = f"TRX-{uuid.uuid4().hex[:8].upper()}"
    parent_sku = parent_sku_for_ean(ean)

    payload: dict[str, object] = {
        "store_region": "ENG",
        "parent_sku": parent_sku,
        "detected_quantity": int(total_units),
        "physical_location": fixture_id,
        "detected_format": _detected_format_for_exception(exception_type),
        "loose_units_visible": int(damaged_units),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence_score": 0.99,
        "ean": ean,
        "edge_trace_id": trx_id,
        "exception_type": exception_type,
        "units_lost": int(units_lost),
        "fixture_id": fixture_id,
        "product_name": product_name,
    }
    if expected_ean:
        payload["expected_ean"] = expected_ean

    response = requests.post(
        _cv_webhook_url(),
        json=payload,
        headers=_edge_headers(),
        timeout=10,
    )
    return response, trx_id
