"""Static catalogs, baseline flattop manifests, and dashboard session key constants."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import streamlit as st

from services.shopfloor_catalog import catalog_by_product_name, load_master_catalog

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
API_KEY = os.getenv("WIP_API_KEY", "dev-wip-engine-key")

DEFAULT_SHRINK_UNIT_PRICE_GBP = 2.50

DASHBOARD_CONTAINERS_KEY = "dashboard_containers"
DASHBOARD_METRICS_KEY = "dashboard_metrics"
DASHBOARD_OFFLINE_FILLS_KEY = "dashboard_offline_fill_audit"
DASHBOARD_INVENTORY_GAP_KEY = "dashboard_inventory_gap_audit"
DASHBOARD_OFFLINE_GAP_EXCEPTIONS_KEY = "dashboard_offline_gap_exceptions"
DASHBOARD_ACTIVE_EXCEPTIONS_KEY = "dashboard_active_exceptions"
DASHBOARD_MANIFEST_AUTO_CONFIRM_KEY = "dashboard_manifest_auto_confirm_audit"
USE_CACHED_TELEMETRY_KEY = "dashboard_use_cached_telemetry"
DASHBOARD_FORCE_EMPTY_TELEMETRY_KEY = "dashboard_force_empty_telemetry"
FLATTOP_QUEUE_CLEARED_KEY = "flattop_queue_cleared_by_purge"
RECONCILIATION_LOG_SESSION_KEY = "reconciliation_log"
KPI_SESSION_DETECTED_PHANTOM_DRIFT = "Detected Phantom Drift Units"
KPI_SESSION_DAILY_SHRINK_COST = "Daily Shrink Cost"
KPI_SESSION_PENDING_EDGE_TASKS = "Pending Edge Tasks"
KPI_SESSION_DAILY_WASTE_QTY = "Daily Waste QTY"
KPI_SESSION_DAILY_WASTE_COST = "Daily Waste Cost"

DASHBOARD_ACTIVE_TAB_KEY = "dashboard_active_tab"
EDGE_AI_TAB_LOADED_KEY = "dashboard_edge_ai_sqlite_loaded"
BOUNCER_TAB_LOADED_KEY = "dashboard_bouncer_api_loaded"

TAB_SYSTEM_OVERVIEW = "System Overview"
TAB_TELEMETRY = "Telemetry & Exceptions"
TAB_OFFLINE_FILL = "Offline Fill"
TAB_EDGE_AI = "Edge AI Autonomy"
TAB_API_BOUNCER = "API Bouncer"
TAB_SHOPFLOOR_SCENARIOS = "Shopfloor Scenarios"
DASHBOARD_TABS = [
    TAB_SYSTEM_OVERVIEW,
    TAB_TELEMETRY,
    TAB_OFFLINE_FILL,
    TAB_EDGE_AI,
    TAB_API_BOUNCER,
    TAB_SHOPFLOOR_SCENARIOS,
]

TOTAL_POWER_CUT_STATUS = "Mandatory Full Gap Scan Required"

OFFLINE_FILL_AUDIT_SKU = "PASTA-CASE-12"
OFFLINE_FILL_AUDIT_ACTION = "fill"
OFFLINE_FILL_AUDIT_QUANTITY = 12

EDGE_CAMERA_NETWORK_STATE = "[STATE: DISCONNECTED_AUTONOMY]"

REPO_ROOT = Path(__file__).resolve().parent
EDGE_AI_WEIGHTS_PATH = REPO_ROOT / "local_sku_weights_ft05.json"
EDGE_AI_BUFFER_PATH = REPO_ROOT / "offline_detection_buffer_ft05.db"

FLATTOP_CARD_CONTAINER_KWARGS = {"border": True, "width": "stretch"}

OFFLINE_CASE_EXPECTED_UNITS = {
    OFFLINE_FILL_AUDIT_SKU: OFFLINE_FILL_AUDIT_QUANTITY,
    "RICE-CASE-6": 6,
}

MOCK_FLATTOP_BACKLOG: list[dict] = [
    {
        "flattop_id": "FT-02",
        "status": "ABANDONED_MID_SHIFT",
        "skus": [
            {
                "sku": "BAKED-BEANS-6PK",
                "ean": "5012345678901",
                "product_name": "Heinz Baked Beans 6pk",
                "bom_units": 12,
            }
        ],
        "trx_ids": [],
    },
    {
        "flattop_id": "FT-03",
        "status": "ABANDONED_MID_SHIFT",
        "skus": [
            {
                "sku": "ORANGE-SODA-8PK",
                "ean": "5012345678948",
                "product_name": "Orange Soda 8pk",
                "bom_units": 8,
            }
        ],
        "trx_ids": [],
    },
    {
        "flattop_id": "FT-04",
        "status": "ABANDONED_MID_SHIFT",
        "skus": [
            {
                "sku": "LAGER-4PK",
                "ean": "5012345678962",
                "product_name": "Lager 4pk",
                "bom_units": 6,
            }
        ],
        "trx_ids": [],
    },
]

MASTER_CATALOG = load_master_catalog()
CATALOG_BY_NAME = catalog_by_product_name()
SHELF_PRODUCT_NAMES = [
    row["product_name"] for row in MASTER_CATALOG if row["fixture_type"] == "SHELF"
]
ALL_PRODUCT_NAMES = [row["product_name"] for row in MASTER_CATALOG]
CATALOG_BY_EAN = {row["ean"]: row["product_name"] for row in MASTER_CATALOG}
CATALOG_ROW_BY_EAN = {row["ean"]: row for row in MASTER_CATALOG}


def default_mock_flattop_backlog() -> list[dict]:
    """Immutable baseline queue — FT-02, FT-03, FT-04 (matches WipEngine mock containers)."""
    return copy.deepcopy(MOCK_FLATTOP_BACKLOG)


def baseline_flattop_ids() -> frozenset[str]:
    return frozenset(entry["flattop_id"] for entry in MOCK_FLATTOP_BACKLOG)


def empty_overview_metrics() -> dict:
    return {
        "pending_delivery_cages": 0,
        "active_flattops": 0,
        "detected_phantom_drift": 0,
        "daily_shrink_cost": 0.0,
        "pending_edge_tasks": 0,
        "daily_waste_qty": 0,
        "daily_waste_cost": 0.0,
    }


def catalog_unit_retail_gbp(catalog_row: dict) -> float:
    return round(int(catalog_row["unit_price_pence"]) / 100.0, 2)


def sku_code_from_queue_row(row: dict) -> str:
    if row.get("sku"):
        return str(row["sku"])
    return f"EAN-{row['ean']}"


def shelf_sku_max_capacity(product_name: str) -> int:
    """Inner pack size for shelf damage UI (falls back to BOM/case units)."""
    row = CATALOG_BY_NAME[product_name]
    inner = row.get("inner_pack_units")
    if inner is not None:
        return int(inner)
    return int(row["bom_units"])


def init_session_state_defaults() -> None:
    if "active_ean" not in st.session_state:
        st.session_state.active_ean = []
    if "fixture_type" not in st.session_state:
        st.session_state.fixture_type = ["SHELF"]
    if "sku_alert" not in st.session_state:
        st.session_state.sku_alert = 0
    if "daily_waste_qty" not in st.session_state:
        st.session_state.daily_waste_qty = 0
    if "daily_waste_cost" not in st.session_state:
        st.session_state.daily_waste_cost = 0.00
