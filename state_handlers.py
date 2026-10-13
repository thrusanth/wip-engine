"""Session mutations, resolution callbacks, Scenario B injection, and purge handlers."""

from __future__ import annotations

import copy

import requests
import streamlit as st

from mock_data import (
    API_BASE_URL,
    API_KEY,
    CATALOG_BY_NAME,
    DASHBOARD_ACTIVE_EXCEPTIONS_KEY,
    DASHBOARD_CONTAINERS_KEY,
    DASHBOARD_FORCE_EMPTY_TELEMETRY_KEY,
    DASHBOARD_INVENTORY_GAP_KEY,
    DASHBOARD_MANIFEST_AUTO_CONFIRM_KEY,
    DASHBOARD_METRICS_KEY,
    DASHBOARD_OFFLINE_FILLS_KEY,
    DASHBOARD_OFFLINE_GAP_EXCEPTIONS_KEY,
    FLATTOP_QUEUE_CLEARED_KEY,
    KPI_SESSION_DAILY_SHRINK_COST,
    KPI_SESSION_DAILY_WASTE_COST,
    KPI_SESSION_DAILY_WASTE_QTY,
    KPI_SESSION_DETECTED_PHANTOM_DRIFT,
    KPI_SESSION_PENDING_EDGE_TASKS,
    RECONCILIATION_LOG_SESSION_KEY,
    USE_CACHED_TELEMETRY_KEY,
    catalog_unit_retail_gbp,
    default_mock_flattop_backlog,
    empty_overview_metrics,
    shelf_sku_max_capacity,
    sku_code_from_queue_row,
)
from utils.transmit_scenario import inject_custom_payload


def baseline_flattop_queue_for_purge() -> list[dict]:
    """Baseline FT-02/03/04 with zeroed drift so KPI loops stay at 0 after purge."""
    backlog = default_mock_flattop_backlog()
    for ft in backlog:
        for row in ft.get("skus") or []:
            row["phantom_drift"] = 0
            row["sent_to_backstock"] = 0
    return backlog


def zero_header_kpi_session_keys() -> None:
    st.session_state[KPI_SESSION_DETECTED_PHANTOM_DRIFT] = 0
    st.session_state[KPI_SESSION_DAILY_SHRINK_COST] = 0.0
    st.session_state[KPI_SESSION_PENDING_EDGE_TASKS] = 0
    st.session_state[KPI_SESSION_DAILY_WASTE_QTY] = 0
    st.session_state[KPI_SESSION_DAILY_WASTE_COST] = 0.0
    st.session_state.daily_waste_qty = 0
    st.session_state.daily_waste_cost = 0.0


def merge_missing_baseline_flattops() -> None:
    """Append any baseline FT missing from session — never remove or replace the list."""
    if st.session_state.get(FLATTOP_QUEUE_CLEARED_KEY):
        return
    present = {ft.get("flattop_id") for ft in st.session_state.flattops}
    for entry in default_mock_flattop_backlog():
        if entry["flattop_id"] not in present:
            st.session_state.flattops.append(copy.deepcopy(entry))


def preserve_flattop_backlog_on_load() -> None:
    """Seed baseline once per session; reruns must not wipe or rebuild flattops."""
    if "_flattop_backlog_seeded" not in st.session_state:
        st.session_state._flattop_backlog_seeded = True
        st.session_state.flattops = default_mock_flattop_backlog()
        return
    if not isinstance(st.session_state.get("flattops"), list):
        st.session_state.flattops = default_mock_flattop_backlog()
        return
    merge_missing_baseline_flattops()


def reset_dashboard_master_state() -> None:
    """Surgical clean slate after bouncer purge — keep Streamlit keys, zero KPIs, restore baseline queue."""
    st.session_state[RECONCILIATION_LOG_SESSION_KEY] = []
    st.session_state.flattops = baseline_flattop_queue_for_purge()
    st.session_state[FLATTOP_QUEUE_CLEARED_KEY] = False
    st.session_state.sku_alert = 0
    zero_header_kpi_session_keys()
    empty_metrics = empty_overview_metrics()
    st.session_state[DASHBOARD_CONTAINERS_KEY] = {}
    st.session_state[DASHBOARD_METRICS_KEY] = dict(empty_metrics)
    st.session_state[DASHBOARD_OFFLINE_FILLS_KEY] = []
    st.session_state[DASHBOARD_INVENTORY_GAP_KEY] = []
    st.session_state[DASHBOARD_OFFLINE_GAP_EXCEPTIONS_KEY] = []
    st.session_state[DASHBOARD_ACTIVE_EXCEPTIONS_KEY] = []
    st.session_state[DASHBOARD_MANIFEST_AUTO_CONFIRM_KEY] = []
    st.session_state[USE_CACHED_TELEMETRY_KEY] = True
    st.session_state[DASHBOARD_FORCE_EMPTY_TELEMETRY_KEY] = True


def clear_dashboard_master_reset_flags() -> None:
    """Resume live WIP telemetry after a new shopfloor injection."""
    st.session_state[DASHBOARD_FORCE_EMPTY_TELEMETRY_KEY] = False
    st.session_state[FLATTOP_QUEUE_CLEARED_KEY] = False


def flattop_id_is_active(flattop_id: str) -> bool:
    return any(
        ft.get("flattop_id") == flattop_id and ft.get("status") == "ABANDONED_MID_SHIFT"
        for ft in st.session_state.flattops
    )


def sync_scenario_a_on_sku_change() -> None:
    from mock_data import SHELF_PRODUCT_NAMES

    product_name = st.session_state.get("shopfloor_a_sku") or SHELF_PRODUCT_NAMES[0]
    max_capacity = shelf_sku_max_capacity(product_name)
    st.session_state.scenario_a_max_capacity = max_capacity
    st.session_state.filled_qty = max_capacity
    st.session_state.damaged_qty = 0


def scenario_a_update_fill() -> None:
    max_capacity = int(st.session_state.scenario_a_max_capacity)
    st.session_state.damaged_qty = max_capacity - int(st.session_state.filled_qty)


def scenario_a_update_damage() -> None:
    max_capacity = int(st.session_state.scenario_a_max_capacity)
    st.session_state.filled_qty = max_capacity - int(st.session_state.damaged_qty)


def merge_backend_waste_metrics(metrics: dict) -> dict:
    """Pull H&S waste KPIs from backend SQLite (survives cached telemetry reruns)."""
    try:
        response = requests.get(f"{API_BASE_URL}/telemetry", timeout=3)
        if response.status_code == 200:
            backend_metrics = response.json().get("metrics", {})
            merged = dict(metrics)
            merged["daily_waste_qty"] = backend_metrics.get(
                "daily_waste_qty", merged.get("daily_waste_qty", 0)
            )
            merged["daily_waste_cost"] = backend_metrics.get(
                "daily_waste_cost", merged.get("daily_waste_cost", 0.0)
            )
            return merged
    except requests.exceptions.RequestException:
        pass
    return metrics


def sync_kpi_session_state(metrics: dict) -> None:
    """Persist H&S waste KPIs in Streamlit session across reruns."""
    backend_waste_qty = int(metrics.get("daily_waste_qty") or 0)
    backend_waste_cost = float(metrics.get("daily_waste_cost") or 0.0)
    st.session_state.daily_waste_qty = max(
        int(st.session_state.daily_waste_qty), backend_waste_qty
    )
    st.session_state.daily_waste_cost = max(
        float(st.session_state.daily_waste_cost), backend_waste_cost
    )


def is_offline_gap_exception(exc: dict) -> bool:
    if exc.get("status") == "Gap Scan Recommended":
        return True
    message = (exc.get("message") or "").lower()
    return "gap scan recommended" in message


def extract_offline_recovery_payload(payload: dict) -> tuple[list, list, list]:
    """Offline recovery data only — kept separate from live flattop telemetry."""
    offline_fill_audit = payload.get("offline_fill_audit", [])
    inventory_gap_audit = payload.get("inventory_gap_audit", [])
    offline_gap_exceptions = [
        exc
        for exc in payload.get("active_exceptions", [])
        if is_offline_gap_exception(exc)
    ]
    return offline_fill_audit, inventory_gap_audit, offline_gap_exceptions


def persist_dashboard_telemetry(payload: dict) -> None:
    """Store latest telemetry in session so cards re-render with updated metrics."""
    st.session_state[DASHBOARD_CONTAINERS_KEY] = payload.get("containers", {})
    metrics = dict(payload.get("metrics") or {})
    metrics["daily_waste_qty"] = st.session_state.daily_waste_qty
    metrics["daily_waste_cost"] = st.session_state.daily_waste_cost
    st.session_state[DASHBOARD_METRICS_KEY] = metrics
    offline_fills, gap_audit, gap_exceptions = extract_offline_recovery_payload(payload)
    st.session_state[DASHBOARD_OFFLINE_FILLS_KEY] = offline_fills
    st.session_state[DASHBOARD_INVENTORY_GAP_KEY] = gap_audit
    st.session_state[DASHBOARD_OFFLINE_GAP_EXCEPTIONS_KEY] = gap_exceptions
    st.session_state[DASHBOARD_ACTIVE_EXCEPTIONS_KEY] = payload.get("active_exceptions", [])
    st.session_state[DASHBOARD_MANIFEST_AUTO_CONFIRM_KEY] = payload.get(
        "manifest_auto_confirm_audit", []
    )
    st.session_state[USE_CACHED_TELEMETRY_KEY] = True


def register_injected_flattop_with_backend(
    flattop_id: str, catalog_rows: list[dict]
) -> bool:
    """Register dynamic Scenario B flattop in WipEngine (same IDs/SKUs as resolution UI)."""
    payload = {
        "container_id": flattop_id,
        "status": "ABANDONED_MID_SHIFT",
        "zone": "Abandoned Flattop",
        "skus": [
            {
                "sku": f"EAN-{row['ean']}",
                "name": row["product_name"],
                "ean": row["ean"],
                "expected": int(row["bom_units"]),
            }
            for row in catalog_rows
        ],
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/events/register-flattop",
            json=payload,
            headers={"X-API-Key": API_KEY},
            timeout=3,
        )
        if response.status_code != 200:
            st.error(
                f"Failed to register flattop {flattop_id} with backend "
                f"({response.status_code}): {response.text}"
            )
            return False
        persist_dashboard_telemetry(response.json())
        return True
    except requests.exceptions.Timeout:
        st.warning(
            f"Backend API timed out while registering flattop {flattop_id}."
        )
        return False
    except requests.exceptions.RequestException as exc:
        st.error(f"Failed to register flattop with backend: {exc}")
        return False


def load_dashboard_telemetry_from_session() -> tuple[dict | None, dict | None]:
    if not st.session_state.get(USE_CACHED_TELEMETRY_KEY):
        return None, None
    st.session_state[USE_CACHED_TELEMETRY_KEY] = False
    return (
        st.session_state.get(DASHBOARD_CONTAINERS_KEY),
        st.session_state.get(DASHBOARD_METRICS_KEY),
    )


def apply_all_found_to_flattop_queue(
    container_id: str,
    sku: str,
    recovered_units: int,
    *,
    outstanding_before: int = 0,
) -> None:
    """Zero session queue phantom drift after All Found so dynamic KPIs drop immediately."""
    recovered = max(0, int(recovered_units))
    if recovered <= 0:
        recovered = max(0, int(outstanding_before))
    target_sku = str(sku)
    for ft in st.session_state.flattops:
        if str(ft.get("flattop_id")) != str(container_id):
            continue
        if ft.get("status") != "ABANDONED_MID_SHIFT":
            continue
        for row in ft.get("skus") or []:
            if sku_code_from_queue_row(row) != target_sku:
                continue
            if recovered <= 0:
                recovered = int(
                    row.get("phantom_drift", row.get("bom_units", 0))
                )
            row["phantom_drift"] = 0
            row["sent_to_backstock"] = int(row.get("sent_to_backstock", 0)) + recovered
            return


def catalog_rows_to_flattop_queue_skus(catalog_rows: list[dict]) -> list[dict]:
    """Bouncer / Scenario B queue rows with explicit phantom drift and unit price."""
    queue_skus: list[dict] = []
    for row in catalog_rows:
        bom = int(row["bom_units"])
        queue_skus.append(
            {
                **row,
                "phantom_drift": bom,
                "price": catalog_unit_retail_gbp(row),
            }
        )
    return queue_skus


def append_abandoned_flattop_to_session_queue(
    flattop_id: str,
    queue_skus: list[dict],
    trx_ids: list[str],
) -> None:
    """Append or replace an active flattop manifest after API Bouncer Scenario B ingest."""
    clear_dashboard_master_reset_flags()
    entry = {
        "flattop_id": flattop_id,
        "status": "ABANDONED_MID_SHIFT",
        "skus": copy.deepcopy(queue_skus),
        "trx_ids": list(trx_ids),
    }
    flattops = st.session_state.flattops
    for index, ft in enumerate(flattops):
        if ft.get("flattop_id") == flattop_id:
            flattops[index] = entry
            return
    flattops.insert(0, entry)


def submit_resolution(
    container_id,
    sku,
    resolution_type,
    recovered_units=0,
    *,
    outstanding_before: int = 0,
    partial_flag_key: str | None = None,
):
    """Submits a resolution event to the FastAPI backend."""
    payload = {
        "container_id": container_id,
        "sku": sku,
        "resolution_type": resolution_type,
        "recovered_units": recovered_units,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/events/resolve",
            json=payload,
            headers={"X-API-Key": API_KEY},
            timeout=3,
        )
        if response.status_code != 200:
            st.error(f"Failed to submit resolution. Error {response.status_code}: {response.text}")
            st.stop()
        resolution_payload = response.json()
        if resolution_type == "all":
            apply_all_found_to_flattop_queue(
                container_id,
                sku,
                recovered_units,
                outstanding_before=outstanding_before,
            )
        persist_dashboard_telemetry(resolution_payload)
        if partial_flag_key is not None:
            st.session_state[partial_flag_key] = False
        st.rerun()
    except requests.exceptions.Timeout:
        st.warning(f"Backend API timed out while submitting resolution for container {container_id}.")
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to submit resolution due to connection error: {e}")
        st.stop()


def handle_scenario_b_injection(flattop_id: str, selected_names: list[str]) -> None:
    """API Bouncer ABANDONED_FLATTOP inject → session flattop queue + optional WIP register."""
    if not selected_names:
        st.warning("Select at least one flattop SKU.")
        return
    if flattop_id_is_active(flattop_id):
        st.warning(f"Flattop {flattop_id} is already active in the telemetry queue.")
        return

    trx_ids: list[str] = []
    errors: list[str] = []
    for name in selected_names:
        row = CATALOG_BY_NAME[name]
        response, trx_id = inject_custom_payload(
            ean=row["ean"],
            product_name=name,
            exception_type="ABANDONED_FLATTOP",
            total_units=int(row["bom_units"]),
            damaged_units=0,
            fixture_id=flattop_id,
        )
        if response.status_code == 200:
            trx_ids.append(trx_id)
        else:
            errors.append(f"{name}: {response.status_code} {response.text}")

    if trx_ids and not errors:
        catalog_rows = [CATALOG_BY_NAME[name] for name in selected_names]
        queue_skus = catalog_rows_to_flattop_queue_skus(catalog_rows)
        if not register_injected_flattop_with_backend(flattop_id, catalog_rows):
            st.warning(
                f"WIP register failed for {flattop_id} — flattop queued locally "
                "for shrink telemetry; resolve actions may 404 until register succeeds."
            )
        append_abandoned_flattop_to_session_queue(flattop_id, queue_skus, trx_ids)
        st.session_state.active_ean = [catalog_rows[0]["ean"]]
        st.session_state.fixture_type = [flattop_id]
        st.session_state.sku_alert = 1
        st.toast(
            f"✅ Injected {len(trx_ids)} flattop event(s): {', '.join(trx_ids)}"
        )
        st.rerun()
    elif trx_ids:
        st.error(
            "Partial inject failure — flattop queue entry was not created. "
            "Resolve errors and try again."
        )
    for err in errors:
        st.error(err)


def handle_purge_reconciliation_log() -> bool:
    """DELETE bouncer WAL + surgical dashboard reset. Returns True on success."""
    try:
        response = requests.delete(f"{API_BASE_URL}/bouncer/purge", timeout=5)
        if response.status_code == 200:
            reset_dashboard_master_state()
            return True
        st.error(f"Purge failed ({response.status_code}): {response.text}")
    except requests.exceptions.RequestException as exc:
        st.error(f"Purge failed: {exc}")
    return False
