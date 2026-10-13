"""Static catalogs, baseline flattop manifests, and dashboard session key constants."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from uuid import uuid4

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

FLATTOP_FLEET_IDS: list[str] = ["FT-01", "FT-02", "FT-03", "FT-04", "FT-05"]
FLATTOP_BACKEND_REGISTERED_KEY = "_flattops_backend_registered"
MANIFEST_INSTANCE_SEQ_KEY = "_manifest_instance_seq"
SESSION_DAILY_SHRINK_FROM_QUEUE_KEY = "session_daily_shrink_from_queue_gbp"


def canonical_flattop_id(raw_id: str | dict) -> str:
    """Normalize dashboard/API container ids to official fleet format (e.g. FT-02)."""
    if isinstance(raw_id, dict):
        slot = raw_id.get("flattop_id") or raw_id.get("id") or ""
    else:
        slot = raw_id
    return str(slot).strip().upper()


# Idle fleet slots injectable via Scenario B (FT-02 is baseline backlog only — use FT-05).
SCENARIO_B_FLATTOP_INJECTION_POOL: list[str] = ["FT-01", "FT-05"]

FLATTOP_STATUS_ABANDONED = "ABANDONED_MID_SHIFT"
FLATTOP_STATUS_RESOLVED_HISTORICAL = "RESOLVED_HISTORICAL"
FLATTOP_UI_DISPLAY_STATUSES = frozenset(
    {FLATTOP_STATUS_ABANDONED, FLATTOP_STATUS_RESOLVED_HISTORICAL}
)


def flattop_queue_sku_is_resolved(row: dict) -> bool:
    return bool(row.get("is_resolved") or row.get("resolved"))


def flattop_all_skus_resolved(ft: dict) -> bool:
    sku_rows = ft.get("skus") or []
    return bool(sku_rows) and all(flattop_queue_sku_is_resolved(row) for row in sku_rows)


def flattop_is_active_on_board(ft: dict) -> bool:
    """True while a manifest is on the queue and still has unresolved SKU work."""
    if ft.get("status") == FLATTOP_STATUS_RESOLVED_HISTORICAL:
        return False
    if ft.get("status") != FLATTOP_STATUS_ABANDONED:
        return False
    if not (ft.get("skus") or []):
        return False
    return not flattop_all_skus_resolved(ft)


def new_manifest_instance_id(fleet_id: str) -> str:
    """Unique backlog key: fleet id + compact suffix (seq + 6-char hash), e.g. FT-05#seq0042-6adf8b."""
    seq = int(st.session_state.get(MANIFEST_INSTANCE_SEQ_KEY, 0)) + 1
    st.session_state[MANIFEST_INSTANCE_SEQ_KEY] = seq
    short_hash = uuid4().hex[:6]
    compact_suffix = f"seq{seq:04d}-{short_hash}"
    return f"{canonical_flattop_id(fleet_id)}#{compact_suffix}"


def flattop_manifest_key(ft: dict) -> str:
    return str(ft.get("manifest_instance_id") or canonical_flattop_id(ft))


def compact_instance_id_for_display(manifest_instance_id: str) -> str:
    """Short badge label after '#', e.g. seq0042-6adf8b (legacy long ids truncated for display)."""
    if "#" not in manifest_instance_id:
        return ""
    suffix = manifest_instance_id.split("#", 1)[1].strip()
    if suffix.startswith("seq") and "-" in suffix:
        return suffix
    # Legacy timestamp-style ids — show trailing hash segment or last 8 chars
    if "-" in suffix:
        tail = suffix.rsplit("-", 1)[-1]
        if len(tail) >= 6:
            return tail[:8]
    return suffix[:12] if len(suffix) > 12 else suffix


def ensure_historical_manifest_instance_ids(flattops: list[dict]) -> None:
    """Backfill instance ids on legacy RESOLVED_HISTORICAL rows (in-place)."""
    for ft in flattops:
        if ft.get("status") != FLATTOP_STATUS_RESOLVED_HISTORICAL:
            continue
        if ft.get("manifest_instance_id"):
            continue
        ft["manifest_instance_id"] = new_manifest_instance_id(ft.get("flattop_id", ""))


def kpi_live_phantom_drift_units_for_row(row: dict) -> int:
    """Unresolved phantom drift only (live shrink risk)."""
    if flattop_queue_sku_is_resolved(row):
        return 0
    return max(0, int(row.get("phantom_drift", 0)))


def kpi_shrink_units_for_row(row: dict) -> int:
    """Units that count toward daily shrink cost (live drift or finalized write-offs)."""
    if flattop_queue_sku_is_resolved(row):
        resolution = row.get("resolution_type")
        if resolution == "none":
            return max(
                0,
                int(row.get("finalized_shrink_units", row.get("shrink_confirmed", 0))),
            )
        if resolution == "partial":
            return max(0, int(row.get("shrink_confirmed", 0)))
        return 0
    return max(0, int(row.get("phantom_drift", 0)))


def flattop_is_displayable_in_ui(ft: dict) -> bool:
    """Queue rows that should render as cards (live or resolved historical)."""
    if ft.get("status") not in FLATTOP_UI_DISPLAY_STATUSES:
        return False
    return bool(ft.get("skus"))


def is_scenario_b_injection_pool_id(flattop_id: str | dict) -> bool:
    return canonical_flattop_id(flattop_id) in SCENARIO_B_FLATTOP_INJECTION_POOL


def available_flattops_for_scenario_b(flattops: list[dict] | None = None) -> list[str]:
    """Flattop IDs eligible for Scenario B inject — pool minus manifests actively on the board."""
    queue = flattops or []
    active_ids = {
        canonical_flattop_id(ft) for ft in queue if flattop_is_active_on_board(ft)
    }
    return [
        ft_id for ft_id in SCENARIO_B_FLATTOP_INJECTION_POOL if ft_id not in active_ids
    ]


def sync_scenario_b_available_flattops_pool(flattops: list[dict] | None = None) -> list[str]:
    """Mirror injection pool into session for UI/helpers (recomputed after each resolution)."""
    options = available_flattops_for_scenario_b(flattops)
    st.session_state["available_flattops"] = options
    return options


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
