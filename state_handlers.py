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
    FLATTOP_BACKEND_REGISTERED_KEY,
    MANIFEST_INSTANCE_SEQ_KEY,
    FLATTOP_QUEUE_CLEARED_KEY,
    KPI_SESSION_DAILY_SHRINK_COST,
    KPI_SESSION_DAILY_WASTE_COST,
    KPI_SESSION_DAILY_WASTE_QTY,
    KPI_SESSION_DETECTED_PHANTOM_DRIFT,
    KPI_SESSION_PENDING_EDGE_TASKS,
    RECONCILIATION_LOG_SESSION_KEY,
    USE_CACHED_TELEMETRY_KEY,
    canonical_flattop_id,
    fleet_id_from_container_ref,
    fleet_slot_occupied_by_queue_entry,
    flattop_manifest_key,
    manifest_fleet_id,
    SCENARIO_B_FLATTOP_INJECTION_POOL,
    catalog_unit_retail_gbp,
    default_mock_flattop_backlog,
    empty_overview_metrics,
    FLATTOP_STATUS_ABANDONED,
    FLATTOP_STATUS_RESOLVED_HISTORICAL,
    SESSION_DAILY_SHRINK_FROM_QUEUE_KEY,
    ensure_historical_manifest_instance_ids,
    ensure_manifest_fleet_metadata,
    flattop_all_skus_resolved,
    initialize_live_flattop_sku_telemetry,
    flattop_sku_unaccounted_variance,
    compute_queue_at_risk_totals,
    flattop_is_active_on_board,
    new_manifest_instance_id,
    shelf_sku_max_capacity,
    sku_code_from_queue_row,
    standardize_flattop_queue_entry,
    sync_scenario_b_available_flattops_pool,
)
from utils.transmit_scenario import inject_custom_payload


def baseline_flattop_queue_for_purge() -> list[dict]:
    """Baseline historical FT-02/03/04 with balanced All Found telemetry after purge."""
    return default_mock_flattop_backlog()


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
    present_baseline_fleets = {
        manifest_fleet_id(ft)
        for ft in st.session_state.flattops
        if ft.get("is_baseline_seed")
    }
    for entry in default_mock_flattop_backlog():
        if entry["flattop_id"] not in present_baseline_fleets:
            st.session_state.flattops.append(copy.deepcopy(entry))


def preserve_flattop_backlog_on_load() -> None:
    """Seed baseline once per session; reruns must not wipe or rebuild flattops."""
    if "_flattop_backlog_seeded" not in st.session_state:
        st.session_state._flattop_backlog_seeded = True
        st.session_state.flattops = default_mock_flattop_backlog()
        sync_scenario_b_available_flattops_pool(st.session_state.flattops)
        return
    if not isinstance(st.session_state.get("flattops"), list):
        st.session_state.flattops = default_mock_flattop_backlog()
        return
    merge_missing_baseline_flattops()
    ensure_manifest_fleet_metadata(st.session_state.get("flattops") or [])
    finalize_resolved_injection_flattops_for_backlog()


def reset_dashboard_master_state() -> None:
    """Surgical clean slate after bouncer purge — keep Streamlit keys, zero KPIs, restore baseline queue."""
    st.session_state[RECONCILIATION_LOG_SESSION_KEY] = []
    st.session_state.flattops = baseline_flattop_queue_for_purge()
    st.session_state[FLATTOP_QUEUE_CLEARED_KEY] = False
    st.session_state.sku_alert = 0
    zero_header_kpi_session_keys()
    st.session_state[SESSION_DAILY_SHRINK_FROM_QUEUE_KEY] = 0.0
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
    st.session_state.pop(FLATTOP_BACKEND_REGISTERED_KEY, None)
    st.session_state[MANIFEST_INSTANCE_SEQ_KEY] = 0


def clear_dashboard_master_reset_flags() -> None:
    """Resume live WIP telemetry after a new shopfloor injection."""
    st.session_state[DASHBOARD_FORCE_EMPTY_TELEMETRY_KEY] = False
    st.session_state[FLATTOP_QUEUE_CLEARED_KEY] = False


def flattop_id_is_active(flattop_id: str) -> bool:
    """True when a fleet slot is held by a live ABANDONED manifest on the queue."""
    target = fleet_id_from_container_ref(flattop_id)
    return any(
        manifest_fleet_id(ft) == target and fleet_slot_occupied_by_queue_entry(ft)
        for ft in st.session_state.flattops
    )


def finalize_resolved_injection_flattops_for_backlog() -> None:
    """Archive any fully resolved fleet manifest (FT-01…FT-05) and release its slot to the inject pool."""
    queue = st.session_state.get("flattops") or []
    ensure_historical_manifest_instance_ids(queue)
    retained: list[dict] = []
    archives: list[dict] = []
    for ft in queue:
        fleet_slot = manifest_fleet_id(ft)
        if fleet_slot not in SCENARIO_B_FLATTOP_INJECTION_POOL:
            retained.append(ft)
            continue
        if (
            ft.get("status") == FLATTOP_STATUS_ABANDONED
            and flattop_all_skus_resolved(ft)
        ):
            archived = copy.deepcopy(ft)
            archived["status"] = FLATTOP_STATUS_RESOLVED_HISTORICAL
            archived["is_baseline_seed"] = False
            # Fresh id per archive — never reuse an existing historical instance tag.
            archived["manifest_instance_id"] = new_manifest_instance_id(
                archived.get("flattop_id", "")
            )
            archives.append(archived)
            continue
        retained.append(ft)
    st.session_state.flattops = retained + archives
    sync_scenario_b_available_flattops_pool(st.session_state.flattops)


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


def _shopfloor_registration_payload_from_queue_flattop(ft: dict) -> dict:
    """Build register-flattop JSON from session queue rows (does not mutate queue telemetry)."""
    fleet_id = canonical_flattop_id(ft)
    sku_items: list[dict] = []
    for row in ft.get("skus") or []:
        expected = int(row.get("expected_qty", row.get("bom_units", 0)))
        sku_items.append(
            {
                "sku": sku_code_from_queue_row(row),
                "name": str(row.get("product_name") or ""),
                "ean": str(row.get("ean") or ""),
                "expected": expected,
            }
        )
    return {
        "container_id": fleet_id,
        "status": ft.get("status") or "ABANDONED_MID_SHIFT",
        "zone": "Abandoned Flattop",
        "skus": sku_items,
    }


def _backend_container_covers_queue_flattop(containers: dict, ft: dict) -> bool:
    """True when WipEngine already knows this flattop id and every queue SKU code."""
    fleet_id = canonical_flattop_id(ft)
    container = containers.get(fleet_id)
    if not container:
        return False
    backend_skus = {str(s.get("sku")) for s in container.get("skus") or []}
    queue_skus = ft.get("skus") or []
    if not queue_skus:
        return False
    for row in queue_skus:
        if sku_code_from_queue_row(row) not in backend_skus:
            return False
    return True


def register_flattop_with_backend(
    ft: dict,
    *,
    persist_telemetry: bool = True,
) -> bool:
    """POST session flattop manifest to WipEngine (queue telemetry is never modified here)."""
    payload = _shopfloor_registration_payload_from_queue_flattop(ft)
    fleet_id = payload["container_id"]
    if not payload["skus"]:
        return False
    try:
        response = requests.post(
            f"{API_BASE_URL}/events/register-flattop",
            json=payload,
            headers={"X-API-Key": API_KEY},
            timeout=3,
        )
        if response.status_code != 200:
            st.error(
                f"Failed to register flattop {fleet_id} with backend "
                f"({response.status_code}): {response.text}"
            )
            return False
        if persist_telemetry:
            persist_dashboard_telemetry(response.json())
        return True
    except requests.exceptions.Timeout:
        st.warning(f"Backend API timed out while registering flattop {fleet_id}.")
        return False
    except requests.exceptions.RequestException as exc:
        st.error(f"Failed to register flattop with backend: {exc}")
        return False


def ensure_session_flattops_registered_with_backend() -> None:
    """Once per session: register any active queue flattops missing from WipEngine (avoids resolve 404)."""
    if st.session_state.get(FLATTOP_BACKEND_REGISTERED_KEY):
        return

    containers: dict = {}
    try:
        response = requests.get(
            f"{API_BASE_URL}/telemetry",
            headers={"X-API-Key": API_KEY},
            timeout=3,
        )
        if response.status_code == 200:
            containers = response.json().get("containers") or {}
    except requests.exceptions.RequestException:
        pass

    for ft in st.session_state.get("flattops") or []:
        if ft.get("status") != "ABANDONED_MID_SHIFT":
            continue
        if _backend_container_covers_queue_flattop(containers, ft):
            continue
        register_flattop_with_backend(ft, persist_telemetry=False)

    st.session_state[FLATTOP_BACKEND_REGISTERED_KEY] = True


def register_injected_flattop_with_backend(
    flattop_id: str, catalog_rows: list[dict]
) -> bool:
    """Register dynamic Scenario B flattop in WipEngine (same IDs/SKUs as resolution UI)."""
    queue_skus = catalog_rows_to_flattop_queue_skus(catalog_rows)
    ft = {
        "flattop_id": canonical_flattop_id(flattop_id),
        "status": "ABANDONED_MID_SHIFT",
        "skus": queue_skus,
    }
    return register_flattop_with_backend(ft, persist_telemetry=True)


def _find_flattop_manifest_by_instance_id(manifest_instance_id: str) -> dict | None:
    target = str(manifest_instance_id).strip()
    for ft in st.session_state.get("flattops") or []:
        if flattop_manifest_key(ft) == target:
            return ft
    return None


def load_dashboard_telemetry_from_session() -> tuple[dict | None, dict | None]:
    if not st.session_state.get(USE_CACHED_TELEMETRY_KEY):
        return None, None
    st.session_state[USE_CACHED_TELEMETRY_KEY] = False
    return (
        st.session_state.get(DASHBOARD_CONTAINERS_KEY),
        st.session_state.get(DASHBOARD_METRICS_KEY),
    )


def _queue_row_phantom_drift(row: dict) -> int:
    return max(0, int(row.get("phantom_drift", 0)))


def _queue_row_unaccounted(row: dict) -> int:
    return flattop_sku_unaccounted_variance(row)


def sync_header_at_risk_kpis_from_queue() -> None:
    """Align cached KPI session keys with queue after resolution (units ↔ cost)."""
    units, cost = compute_queue_at_risk_totals(st.session_state.get("flattops"))
    st.session_state[KPI_SESSION_DETECTED_PHANTOM_DRIFT] = units
    st.session_state[KPI_SESSION_DAILY_SHRINK_COST] = cost
    st.session_state[SESSION_DAILY_SHRINK_FROM_QUEUE_KEY] = cost


def apply_all_found_to_flattop_queue(
    sku: str,
    recovered_units: int,
    *,
    manifest_instance_id: str,
) -> None:
    """Route current unaccounted variance to backstock from live queue row state."""
    del recovered_units
    target_sku = str(sku)
    ft = _find_flattop_manifest_by_instance_id(manifest_instance_id)
    if not ft or ft.get("status") != FLATTOP_STATUS_ABANDONED:
        return
    for row in ft.get("skus") or []:
        if sku_code_from_queue_row(row) != target_sku:
            continue
        unaccounted = _queue_row_unaccounted(row)
        row["sent_to_backstock"] = int(row.get("sent_to_backstock", 0)) + unaccounted
        row["unaccounted_variance"] = 0
        row["is_resolved"] = True
        row["resolved"] = True
        row["resolution_type"] = "all"
        return


def apply_not_found_to_flattop_queue(
    sku: str,
    *,
    manifest_instance_id: str,
) -> None:
    """Move current unaccounted variance into confirmed phantom drift (Not Present)."""
    target_sku = str(sku)
    ft = _find_flattop_manifest_by_instance_id(manifest_instance_id)
    if not ft or ft.get("status") != FLATTOP_STATUS_ABANDONED:
        return
    for row in ft.get("skus") or []:
        if sku_code_from_queue_row(row) != target_sku:
            continue
        unaccounted = _queue_row_unaccounted(row)
        row["phantom_drift"] = _queue_row_phantom_drift(row) + unaccounted
        row["unaccounted_variance"] = 0
        row["finalized_shrink_units"] = row["phantom_drift"]
        row["shrink_confirmed"] = row["phantom_drift"]
        row["recovered_units"] = 0
        row["is_resolved"] = True
        row["resolved"] = True
        row["resolution_type"] = "none"
        return


def _flattop_all_skus_resolved_in_queue(manifest_instance_id: str) -> bool:
    ft = _find_flattop_manifest_by_instance_id(manifest_instance_id)
    if not ft or ft.get("status") != FLATTOP_STATUS_ABANDONED:
        return False
    return flattop_all_skus_resolved(ft)


def maybe_decrement_pending_edge_tasks(
    manifest_instance_id: str, response_payload: dict
) -> None:
    """Drop pending task count when every SKU on the flattop is resolved."""
    ft = _find_flattop_manifest_by_instance_id(manifest_instance_id)
    fleet_id = manifest_fleet_id(ft) if ft else fleet_id_from_container_ref(manifest_instance_id)
    container = (response_payload.get("containers") or {}).get(fleet_id) or {}
    backend_skus = container.get("skus") or []
    backend_cleared = bool(backend_skus) and all(
        row.get("is_resolved") for row in backend_skus
    )
    if backend_cleared or _flattop_all_skus_resolved_in_queue(manifest_instance_id):
        st.session_state[KPI_SESSION_PENDING_EDGE_TASKS] = max(
            0,
            int(st.session_state.get(KPI_SESSION_PENDING_EDGE_TASKS, 0)) - 1,
        )


def apply_partial_to_flattop_queue(
    sku: str,
    recovered_units: int,
    *,
    manifest_instance_id: str,
) -> None:
    """Split current unaccounted variance between backstock (found) and phantom drift."""
    recovered = max(0, int(recovered_units))
    target_sku = str(sku)
    ft = _find_flattop_manifest_by_instance_id(manifest_instance_id)
    if not ft or ft.get("status") != FLATTOP_STATUS_ABANDONED:
        return
    for row in ft.get("skus") or []:
        if sku_code_from_queue_row(row) != target_sku:
            continue
        unaccounted = _queue_row_unaccounted(row)
        recovered = min(recovered, unaccounted)
        shrink_add = max(0, unaccounted - recovered)
        row["sent_to_backstock"] = int(row.get("sent_to_backstock", 0)) + recovered
        row["phantom_drift"] = _queue_row_phantom_drift(row) + shrink_add
        row["unaccounted_variance"] = 0
        row["recovered_units"] = recovered
        row["shrink_confirmed"] = row["phantom_drift"]
        row["is_resolved"] = True
        row["resolved"] = True
        row["resolution_type"] = "partial"
        row["status"] = "Partial Shrink Confirmed"
        return


def catalog_rows_to_flattop_queue_skus(catalog_rows: list[dict]) -> list[dict]:
    """Bouncer / Scenario B queue rows — unaccounted variance is the initial gap; phantom drift starts at 0."""
    queue_skus: list[dict] = []
    for row in catalog_rows:
        bom = int(row["bom_units"])
        sku_row = {
            **row,
            "expected_qty": bom,
            "worked_to_shelf": int(row.get("worked_to_shelf", 0)),
            "sent_to_backstock": int(row.get("sent_to_backstock", 0)),
            "price": catalog_unit_retail_gbp(row),
        }
        initialize_live_flattop_sku_telemetry(sku_row)
        queue_skus.append(sku_row)
    return queue_skus


def append_abandoned_flattop_to_session_queue(
    flattop_id: str,
    queue_skus: list[dict],
    trx_ids: list[str],
) -> None:
    """Append or replace an active flattop manifest after API Bouncer Scenario B ingest."""
    clear_dashboard_master_reset_flags()
    fleet_id = canonical_flattop_id(flattop_id)
    entry = standardize_flattop_queue_entry(
        {
            "flattop_id": fleet_id,
            "status": FLATTOP_STATUS_ABANDONED,
            "skus": queue_skus,
            "trx_ids": list(trx_ids),
        }
    )
    flattops = st.session_state.flattops
    for index, ft in enumerate(flattops):
        if (
            manifest_fleet_id(ft) == fleet_id
            and fleet_slot_occupied_by_queue_entry(ft)
        ):
            flattops[index] = entry
            return
    flattops.insert(0, entry)


def submit_resolution(
    fleet_id,
    sku,
    resolution_type,
    recovered_units=0,
    *,
    manifest_instance_id: str,
    partial_flag_key: str | None = None,
):
    """Submits a resolution event to the FastAPI backend."""
    if resolution_type not in ("all", "none", "partial"):
        st.error(f"Unsupported resolution type: {resolution_type!r}")
        st.stop()
    fleet_container_id = fleet_id_from_container_ref(fleet_id)
    manifest_key = str(manifest_instance_id).strip()
    payload = {
        "container_id": fleet_container_id,
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
                sku,
                recovered_units,
                manifest_instance_id=manifest_key,
            )
        elif resolution_type == "none":
            apply_not_found_to_flattop_queue(
                sku,
                manifest_instance_id=manifest_key,
            )
        elif resolution_type == "partial":
            apply_partial_to_flattop_queue(
                sku,
                recovered_units,
                manifest_instance_id=manifest_key,
            )
        finalize_resolved_injection_flattops_for_backlog()
        sync_header_at_risk_kpis_from_queue()
        maybe_decrement_pending_edge_tasks(manifest_key, resolution_payload)
        persist_dashboard_telemetry(resolution_payload)
        if partial_flag_key is not None:
            st.session_state[partial_flag_key] = False
        st.rerun()
    except requests.exceptions.Timeout:
        st.warning(
            f"Backend API timed out while submitting resolution for {manifest_key}."
        )
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to submit resolution due to connection error: {e}")
        st.stop()


def handle_scenario_b_injection(flattop_id: str, selected_names: list[str]) -> None:
    """API Bouncer ABANDONED_FLATTOP inject → session flattop queue + optional WIP register."""
    if not selected_names:
        st.warning("Select at least one flattop SKU.")
        return
    # GUARDRAIL (keep for future inline SKU add-ons): block duplicate flattop manifests.
    # Reuse this pattern when adding SKUs to an already-active card — e.g. warn if SKU
    # already exists on the flattop, while allowing new SKU lines on the same container id.
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
        sync_scenario_b_available_flattops_pool(st.session_state.flattops)
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
