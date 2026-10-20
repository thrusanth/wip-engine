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
TAB_PDA_VIEW = "PDA View"
PDA_CLEARED_TRACE_IDS_KEY = "pda_cleared_trace_ids"
DASHBOARD_TABS = [
    TAB_SYSTEM_OVERVIEW,
    TAB_TELEMETRY,
    TAB_OFFLINE_FILL,
    TAB_EDGE_AI,
    TAB_API_BOUNCER,
    TAB_SHOPFLOOR_SCENARIOS,
    TAB_PDA_VIEW,
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


def manifest_fleet_id(ft: dict) -> str:
    """Base fleet slot (FT-0X) from queue manifest metadata — not the instance suffix."""
    explicit = ft.get("fleet_id") or ft.get("flattop_id")
    if explicit:
        return str(explicit).strip().upper().split("#", 1)[0].strip()
    return fleet_id_from_container_ref(ft)


def fleet_slot_occupied_by_queue_entry(ft: dict) -> bool:
    """True while a live ABANDONED manifest still holds the fleet slot on the board."""
    if ft.get("status") == FLATTOP_STATUS_RESOLVED_HISTORICAL:
        return False
    if ft.get("status") != FLATTOP_STATUS_ABANDONED:
        return False
    return bool(ft.get("skus"))


def fleet_id_from_container_ref(raw_id: str | dict) -> str:
    """Base fleet id for WipEngine API (strip manifest instance suffix after '#')."""
    if isinstance(raw_id, dict):
        explicit = raw_id.get("fleet_id") or raw_id.get("flattop_id")
        if explicit:
            text = str(explicit).strip().upper()
            return text.split("#", 1)[0].strip()
        slot = raw_id.get("id") or raw_id.get("manifest_instance_id") or ""
    else:
        slot = raw_id
    text = str(slot).strip().upper()
    if "#" in text:
        return text.split("#", 1)[0].strip()
    return text


# Full fleet injectable via Scenario B when no live manifest holds the slot.
SCENARIO_B_FLATTOP_INJECTION_POOL: list[str] = list(FLATTOP_FLEET_IDS)

FLATTOP_STATUS_ABANDONED = "ABANDONED_MID_SHIFT"
FLATTOP_STATUS_RESOLVED_HISTORICAL = "RESOLVED_HISTORICAL"
FLATTOP_UI_DISPLAY_STATUSES = frozenset(
    {FLATTOP_STATUS_ABANDONED, FLATTOP_STATUS_RESOLVED_HISTORICAL}
)


def flattop_queue_sku_is_resolved(row: dict) -> bool:
    return bool(row.get("is_resolved") or row.get("resolved"))


def flattop_sku_expected_qty(row: dict) -> int:
    return int(row.get("expected_qty", row.get("bom_units", 0)))


def flattop_sku_worked_to_shelf(row: dict) -> int:
    return int(row.get("worked_to_shelf", row.get("worked", 0)))


def flattop_sku_sent_to_backstock(row: dict) -> int:
    return int(row.get("sent_to_backstock", 0))


def compute_flattop_sku_unaccounted_variance(row: dict) -> int:
    """Missing units before resolution: Expected − Worked − Backstock."""
    expected = flattop_sku_expected_qty(row)
    worked = flattop_sku_worked_to_shelf(row)
    backstock = flattop_sku_sent_to_backstock(row)
    return max(0, expected - worked - backstock)


def flattop_sku_unaccounted_variance(row: dict) -> int:
    if "unaccounted_variance" in row:
        return max(0, int(row["unaccounted_variance"]))
    if flattop_queue_sku_is_resolved(row):
        return 0
    return compute_flattop_sku_unaccounted_variance(row)


def initialize_live_flattop_sku_telemetry(row: dict) -> None:
    """Scenario B / live ABANDONED rows: phantom drift 0 until shrink is confirmed."""
    row["phantom_drift"] = 0
    row["unaccounted_variance"] = compute_flattop_sku_unaccounted_variance(row)


BASELINE_HISTORICAL_SENT_TO_BACKSTOCK: dict[str, int] = {
    "FT-02": 6,
    "FT-03": 2,
    "FT-04": 3,
}


def enforce_baseline_historical_sku_telemetry(ft: dict) -> None:
    """Lock All Found math for the three static MOCK_FLATTOP_BACKLOG seeds only."""
    if not ft.get("is_baseline_seed"):
        return
    if ft.get("status") != FLATTOP_STATUS_RESOLVED_HISTORICAL:
        return
    fleet_id = manifest_fleet_id(ft)
    if fleet_id not in baseline_flattop_ids():
        return
    backstock = BASELINE_HISTORICAL_SENT_TO_BACKSTOCK[fleet_id]
    for row in ft.get("skus") or []:
        sku_code = str(row.get("sku") or "")
        splits = _BASELINE_SKU_SPLITS.get(sku_code, {})
        expected = int(row.get("expected_qty", splits.get("expected_qty", row.get("bom_units", 0))))
        worked = int(row.get("worked_to_shelf", splits.get("worked_to_shelf", 0)))
        row["expected_qty"] = expected
        row["worked_to_shelf"] = worked
        row["sent_to_backstock"] = backstock
        row["phantom_drift"] = 0
        row["unaccounted_variance"] = 0
        row["is_resolved"] = True
        row["resolved"] = True
        row["resolution_type"] = "all"


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


def flattop_is_pending_edge_task(ft: dict) -> bool:
    """Live ABANDONED manifest with at least one unresolved SKU (not historical backlog)."""
    if ft.get("status") == FLATTOP_STATUS_RESOLVED_HISTORICAL:
        return False
    if ft.get("status") != FLATTOP_STATUS_ABANDONED:
        return False
    for row in ft.get("skus") or []:
        if flattop_queue_sku_is_resolved(row):
            continue
        if flattop_sku_unaccounted_variance(row) > 0:
            return True
    return False


def count_pending_edge_tasks_from_queue(flattops: list[dict] | None = None) -> int:
    """Pending Edge Tasks KPI — session queue only, never backend mock containers."""
    return sum(1 for ft in (flattops or []) if flattop_is_pending_edge_task(ft))


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


def ensure_manifest_fleet_metadata(flattops: list[dict]) -> None:
    """Backfill explicit fleet_id / flattop_id on queue rows (never the instance suffix)."""
    for ft in flattops:
        fleet = manifest_fleet_id(ft)
        ft["fleet_id"] = fleet
        ft["flattop_id"] = fleet


def ensure_historical_manifest_instance_ids(flattops: list[dict]) -> None:
    """Backfill instance ids on legacy RESOLVED_HISTORICAL rows (in-place)."""
    for ft in flattops:
        if ft.get("status") != FLATTOP_STATUS_RESOLVED_HISTORICAL:
            continue
        if ft.get("manifest_instance_id"):
            continue
        ft["manifest_instance_id"] = new_manifest_instance_id(ft.get("flattop_id", ""))


def kpi_live_phantom_drift_units_for_row(row: dict) -> int:
    """Live unknown missing units (unaccounted variance before action)."""
    if flattop_queue_sku_is_resolved(row):
        return 0
    return flattop_sku_unaccounted_variance(row)


def kpi_total_missing_units_for_row(row: dict) -> int:
    """At-risk unit volume: confirmed phantom drift plus live unaccounted variance."""
    phantom = max(0, int(row.get("phantom_drift", 0)))
    unaccounted = flattop_sku_unaccounted_variance(row)
    return phantom + unaccounted


def kpi_detected_phantom_drift_units_for_row(row: dict) -> int:
    """Alias for header KPI — total missing units (drift + unaccounted variance)."""
    return kpi_total_missing_units_for_row(row)


def queue_row_unit_retail_gbp(row: dict) -> float:
    queue_price = row.get("price")
    if queue_price is not None and float(queue_price) > 0:
        return float(queue_price)
    if row.get("unit_price_pence") is not None:
        return catalog_unit_retail_gbp(row)
    return DEFAULT_SHRINK_UNIT_PRICE_GBP


def compute_queue_at_risk_totals(flattops: list[dict] | None) -> tuple[int, float]:
    """Header KPI pair — missing units and retail exposure from session queue rows."""
    total_units = 0
    total_cost = 0.0
    for ft in flattops or []:
        if ft.get("status") not in FLATTOP_UI_DISPLAY_STATUSES:
            continue
        for row in ft.get("skus") or []:
            # Includes live unaccounted_variance and confirmed phantom_drift on
            # RESOLVED_HISTORICAL rows (Not Present / Partial archives).
            missing = kpi_total_missing_units_for_row(row)
            total_units += missing
            if missing > 0:
                total_cost += missing * queue_row_unit_retail_gbp(row)
    return total_units, round(total_cost, 2)


def kpi_shrink_units_for_row(row: dict) -> int:
    """Confirmed shrink only (phantom_drift after resolution — not live unaccounted variance)."""
    if flattop_queue_sku_is_resolved(row):
        resolution = row.get("resolution_type")
        if resolution == "none":
            return max(
                0,
                int(row.get("phantom_drift", row.get("finalized_shrink_units", row.get("shrink_confirmed", 0)))),
            )
        if resolution == "partial":
            return max(0, int(row.get("phantom_drift", row.get("shrink_confirmed", 0))))
        return 0
    return 0


def flattop_is_displayable_in_ui(ft: dict) -> bool:
    """Queue rows that should render as cards (live or resolved historical)."""
    if ft.get("status") not in FLATTOP_UI_DISPLAY_STATUSES:
        return False
    return bool(ft.get("skus"))


def is_scenario_b_injection_pool_id(flattop_id: str | dict) -> bool:
    return fleet_id_from_container_ref(flattop_id) in SCENARIO_B_FLATTOP_INJECTION_POOL


def active_fleet_ids_with_live_manifests(flattops: list[dict] | None = None) -> set[str]:
    """Fleet slots currently held by live ABANDONED manifests (not RESOLVED_HISTORICAL)."""
    queue = flattops or []
    return {
        manifest_fleet_id(ft)
        for ft in queue
        if fleet_slot_occupied_by_queue_entry(ft)
    }


def available_flattops_for_scenario_b(flattops: list[dict] | None = None) -> list[str]:
    """Fleet ids eligible for Scenario B — full pool minus any slot with a live manifest."""
    active_ids = active_fleet_ids_with_live_manifests(flattops)
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

# Baseline SKU telemetry splits (aligned with WipEngine mock containers).
_BASELINE_SKU_SPLITS: dict[str, dict[str, int]] = {
    "BAKED-BEANS-6PK": {
        "expected_qty": 12,
        "worked_to_shelf": 6,
        "sent_to_backstock": 6,
        "phantom_drift": 0,
        "unaccounted_variance": 0,
        "recovered_units": 4,
    },
    "ORANGE-SODA-8PK": {
        "expected_qty": 8,
        "worked_to_shelf": 6,
        "sent_to_backstock": 2,
        "phantom_drift": 0,
        "unaccounted_variance": 0,
        "recovered_units": 2,
    },
    "LAGER-4PK": {
        "expected_qty": 6,
        "worked_to_shelf": 3,
        "sent_to_backstock": 3,
        "phantom_drift": 0,
        "unaccounted_variance": 0,
        "recovered_units": 3,
    },
}

MOCK_FLATTOP_BACKLOG: list[dict] = [
    {
        "flattop_id": "FT-02",
        "is_baseline_seed": True,
        "status": FLATTOP_STATUS_RESOLVED_HISTORICAL,
        "resolution_type": "all",
        "skus": [
            {
                "sku": "BAKED-BEANS-6PK",
                "ean": "5012345678901",
                "product_name": "Heinz Baked Beans 6pk",
                "bom_units": 12,
                "expected_qty": 12,
                "worked_to_shelf": 6,
                "sent_to_backstock": 6,
            }
        ],
        "trx_ids": [],
    },
    {
        "flattop_id": "FT-03",
        "is_baseline_seed": True,
        "status": FLATTOP_STATUS_RESOLVED_HISTORICAL,
        "resolution_type": "all",
        "skus": [
            {
                "sku": "ORANGE-SODA-8PK",
                "ean": "5012345678948",
                "product_name": "Orange Soda 8pk",
                "bom_units": 8,
                "expected_qty": 8,
                "worked_to_shelf": 6,
                "sent_to_backstock": 2,
            }
        ],
        "trx_ids": [],
    },
    {
        "flattop_id": "FT-04",
        "is_baseline_seed": True,
        "status": FLATTOP_STATUS_RESOLVED_HISTORICAL,
        "resolution_type": "all",
        "skus": [
            {
                "sku": "LAGER-4PK",
                "ean": "5012345678962",
                "product_name": "Lager 4pk",
                "bom_units": 6,
                "expected_qty": 6,
                "worked_to_shelf": 3,
                "sent_to_backstock": 3,
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


def standardize_flattop_sku_row(
    row: dict, *, historical_seed: bool = False, baseline_seed: bool = False
) -> dict:
    """One queue SKU line — same keys as Scenario B `catalog_rows_to_flattop_queue_skus` output."""
    sku = copy.deepcopy(row)
    catalog = CATALOG_ROW_BY_EAN.get(str(sku.get("ean") or "").strip(), {})
    sku_code = str(sku.get("sku") or sku_code_from_queue_row({**sku, **catalog}))
    sku["sku"] = sku_code
    bom = int(sku.get("bom_units", catalog.get("bom_units", 0)))
    sku["bom_units"] = bom
    sku["expected_qty"] = int(sku.get("expected_qty", bom))
    sku["product_name"] = str(
        sku.get("product_name") or catalog.get("product_name") or sku_code
    )
    for key, value in catalog.items():
        sku.setdefault(key, value)
    if baseline_seed:
        for key, value in _BASELINE_SKU_SPLITS.get(sku_code, {}).items():
            sku.setdefault(key, value)
    sku.setdefault("phantom_drift", 0)
    sku.setdefault("worked_to_shelf", 0)
    sku.setdefault("sent_to_backstock", 0)
    if "price" not in sku and sku.get("unit_price_pence") is not None:
        sku["price"] = catalog_unit_retail_gbp(sku)
    sku.setdefault("is_resolved", False)
    sku.setdefault("resolved", False)
    if (
        not historical_seed
        and not flattop_queue_sku_is_resolved(sku)
    ):
        initialize_live_flattop_sku_telemetry(sku)
    return sku


def standardize_flattop_queue_entry(
    entry: dict,
    *,
    assign_manifest_instance_id: bool = True,
    trx_ids: list[str] | None = None,
) -> dict:
    """Flattop manifest — universal shape for baseline FT-02/03/04 and Scenario B injects."""
    ft = copy.deepcopy(entry)
    fleet_id = fleet_id_from_container_ref(ft)
    ft["fleet_id"] = fleet_id
    ft["flattop_id"] = fleet_id
    ft["status"] = ft.get("status") or FLATTOP_STATUS_ABANDONED
    if entry.get("is_baseline_seed"):
        ft["is_baseline_seed"] = True
    ft["trx_ids"] = list(trx_ids if trx_ids is not None else ft.get("trx_ids") or [])
    if assign_manifest_instance_id and not ft.get("manifest_instance_id"):
        ft["manifest_instance_id"] = new_manifest_instance_id(fleet_id)
    is_historical = ft.get("status") == FLATTOP_STATUS_RESOLVED_HISTORICAL
    baseline_seed = bool(ft.get("is_baseline_seed"))
    ft["skus"] = [
        standardize_flattop_sku_row(
            row, historical_seed=is_historical, baseline_seed=baseline_seed
        )
        for row in (ft.get("skus") or [])
    ]
    if is_historical and baseline_seed:
        ft.setdefault("resolution_type", "all")
        enforce_baseline_historical_sku_telemetry(ft)
    return ft


def default_mock_flattop_backlog() -> list[dict]:
    """Baseline historical backlog FT-02, FT-03, FT-04 — not live ABANDONED manifests."""
    return [
        standardize_flattop_queue_entry(entry)
        for entry in copy.deepcopy(MOCK_FLATTOP_BACKLOG)
    ]


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
    if PDA_CLEARED_TRACE_IDS_KEY not in st.session_state:
        st.session_state[PDA_CLEARED_TRACE_IDS_KEY] = []
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
