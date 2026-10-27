"""CV format violation interceptor and shelf reconciliation (migrated from api_bouncer)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status

from models.bouncer_schemas import (
    CVEdgeDetection,
    DamageEventPayload,
    ExpectedLedger,
    LabelPrintPayload,
    ShelfReconciliation,
    TransactionEnginePayload,
)
from services.bouncer_buffer import get_reconciliation_by_trace_id, record_reconciliation
from services.product_lookup import resolve_case_size, resolve_product_name
from services.waste_metrics import record_scenario_a_waste
from services.cv_catalog import (
    expected_ledger_from_cv_item,
    resolve_cv_catalog_item,
)
from services.shopfloor_catalog import (
    build_master_ledger_db,
    catalog_by_ean,
    catalog_by_product_name,
    parent_sku_for_ean,
)

MUP_RATE_PER_UNIT = float(os.getenv("BOUNCER_MUP_RATE_PER_UNIT", "0.65"))
CV_MIN_CONFIDENCE_INTACT = 0.80
CV_MIN_CONFIDENCE_DAMAGE = 0.70

_LEGACY_LEDGER: dict[str, ExpectedLedger] = {
    "SKU-WATER-6PK": ExpectedLedger(
        parent_sku="SKU-WATER-6PK",
        ean="5051410987654",
        expected_quantity=20,
        planogram_location="Aisle-4-Bay-2",
        expected_format="SHRINK_WRAPPED_MULTIPACK",
        linked_child_sku="SKU-WATER-SINGLE",
        retail_price=3.00,
        pack_quantity=6,
        is_alcohol=False,
    ),
    "SKU-BEANS-4PK": ExpectedLedger(
        parent_sku="SKU-BEANS-4PK",
        ean="5051420123456",
        expected_quantity=30,
        planogram_location="Aisle-2-Bay-4",
        expected_format="SHRINK_WRAPPED_MULTIPACK",
        linked_child_sku="SKU-BEANS-SINGLE",
        retail_price=2.40,
        pack_quantity=4,
        is_alcohol=False,
    ),
    "SKU-LAGER-4PK": ExpectedLedger(
        parent_sku="SKU-LAGER-4PK",
        ean="5051410112233",
        expected_quantity=15,
        planogram_location="Aisle-4-Bay-1",
        expected_format="SHRINK_WRAPPED_MULTIPACK",
        linked_child_sku="SKU-LAGER-SINGLE",
        retail_price=6.00,
        pack_quantity=4,
        is_alcohol=True,
        abv_strength=4.5,
        volume_litres=0.5,
        excise_duty=0.45,
        vat_amount=0.20,
    ),
    "SKU-CIDER-4PK": ExpectedLedger(
        parent_sku="SKU-CIDER-4PK",
        ean="5051410223344",
        expected_quantity=12,
        planogram_location="Aisle-4-Bay-3",
        expected_format="SHRINK_WRAPPED_MULTIPACK",
        linked_child_sku="SKU-CIDER-SINGLE",
        retail_price=4.00,
        pack_quantity=4,
        is_alcohol=True,
        abv_strength=5.0,
        volume_litres=0.5,
        excise_duty=0.50,
        vat_amount=0.20,
    ),
    "SKU-BEER-10PK": ExpectedLedger(
        parent_sku="SKU-BEER-10PK",
        ean="5051410998877",
        expected_quantity=10,
        planogram_location="Aisle-4-Bay-4",
        expected_format="SHRINK_WRAPPED_MULTIPACK",
        linked_child_sku="SKU-BEER-SINGLE",
        retail_price=11.00,
        pack_quantity=10,
        is_alcohol=True,
        abv_strength=4.0,
        volume_litres=0.44,
        excise_duty=0.40,
        vat_amount=0.18,
    ),
}

def _build_central_ledger_db() -> dict[str, ExpectedLedger]:
    merged: dict[str, ExpectedLedger] = dict(_LEGACY_LEDGER)
    master_ledger = build_master_ledger_db()
    if not isinstance(master_ledger, dict):
        return merged
    for parent_sku, entry in master_ledger.items():
        if isinstance(entry, ExpectedLedger):
            merged[str(parent_sku)] = entry
    return merged


CENTRAL_LEDGER_DB: dict[str, ExpectedLedger] = _build_central_ledger_db()


def _resolve_ledger(payload: CVEdgeDetection) -> ExpectedLedger:
    ledger_data = CENTRAL_LEDGER_DB.get(payload.parent_sku)
    if ledger_data:
        return ledger_data
    if payload.ean:
        parent_key = parent_sku_for_ean(payload.ean)
        ledger_data = CENTRAL_LEDGER_DB.get(parent_key)
        if ledger_data:
            return ledger_data
        for entry in CENTRAL_LEDGER_DB.values():
            if entry.ean == payload.ean:
                return entry
        resolved = resolve_cv_catalog_item(payload.ean)
        if resolved:
            return expected_ledger_from_cv_item(resolved[1])
    if payload.product_name:
        resolved = resolve_cv_catalog_item(payload.product_name)
        if resolved:
            return expected_ledger_from_cv_item(resolved[1])
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found.")


def _ledger_for_ean(ean: str) -> Optional[ExpectedLedger]:
    return CENTRAL_LEDGER_DB.get(parent_sku_for_ean(ean))


def _ledger_is_shrink_wrapped_multipack(ledger_data: ExpectedLedger) -> bool:
    """Ledger-driven multipack check (no product-name parsing)."""
    return ledger_data.expected_format == "SHRINK_WRAPPED_MULTIPACK"


def _is_intact_detection(payload: CVEdgeDetection, ledger_data: ExpectedLedger) -> bool:
    """Healthy stock: presented exactly as the ledger expects, no exception, no loose units."""
    return (
        not payload.exception_type
        and int(payload.loose_units_visible) == 0
        and payload.detected_format == ledger_data.expected_format
    )


def _min_confidence_for_detection(
    payload: CVEdgeDetection, ledger_data: ExpectedLedger
) -> float:
    """Strict floor for INTACT stock; relaxed floor for any damage/exception signal."""
    if _is_intact_detection(payload, ledger_data):
        return CV_MIN_CONFIDENCE_INTACT
    return CV_MIN_CONFIDENCE_DAMAGE


def effective_damage_condition(condition: str, loose_units_visible: int) -> str:
    """Physical evidence beats Luna's label: loose units mean the pack is compromised,
    even if the raw condition says INTACT (e.g. a taped-up multipack)."""
    normalized = condition.strip().upper()
    if normalized == "INTACT" and int(loose_units_visible or 0) > 0:
        return "TORN_MULTIPACK"
    return normalized


def confidence_floor_for_condition(effective_condition: str) -> float:
    """Strict floor for INTACT; relaxed floor for any damage condition."""
    if effective_condition == "INTACT":
        return CV_MIN_CONFIDENCE_INTACT
    return CV_MIN_CONFIDENCE_DAMAGE


def _is_torn_multipack_detection(
    payload: CVEdgeDetection, ledger_data: ExpectedLedger
) -> bool:
    """Vision indicates a broken multipack on a SHRINK_WRAPPED_MULTIPACK ledger line."""
    if not _ledger_is_shrink_wrapped_multipack(ledger_data):
        return False
    return (
        payload.exception_type == "TORN_MULTIPACK"
        or payload.detected_format == "TORN_MULTIPACK"
        or int(payload.loose_units_visible) > 0
    )


def _apply_health_and_safety_writeoff(
    payload: CVEdgeDetection,
    ledger_data: ExpectedLedger,
    *,
    status_code: str,
    format_alert: str,
) -> tuple[str, str, str, TransactionEnginePayload, None]:
    # Total write-off always removes exactly one parent unit, independent of loose_units_visible.
    damaged_qty = 1
    waste_value = round(damaged_qty * ledger_data.retail_price, 2)
    record_scenario_a_waste(damaged_qty, waste_value)
    stock_key = payload.parent_sku
    stock_adj = {stock_key: -damaged_qty}
    writeoff_rule = (
        "NON_COMPLIANT_FOOD_SAFETY [Action: Automatically deducted "
        f"{damaged_qty} from stock record & routed to H&S Waste Profile. 0 yield.]"
    )
    transaction_payload = TransactionEnginePayload(
        transaction_type="HEALTH_AND_SAFETY_WRITEOFF",
        reason_code="DAMAGED_UNSEALED_FOOD_PACK",
        ledger_adjustments=stock_adj,
        compliance_rule_applied=writeoff_rule,
        adjustment_summary=(
            f"Adj: {{'{stock_key}': -{damaged_qty}}} -> DEST: H&S_WASTE_PROFILE"
        ),
    )
    shop_floor_action = (
        "DISPATCH_COLLEAGUE: Bag the damaged items. No manual scanning required "
        "(Waste profile updated automatically)."
    )
    return status_code, format_alert, shop_floor_action, transaction_payload, None


def _apply_torn_multipack_violation(
    payload: CVEdgeDetection,
    ledger_data: ExpectedLedger,
    audit_trace_id: str,
) -> tuple[str, str, str, Optional[TransactionEnginePayload], Optional[LabelPrintPayload]]:
    damaged_qty = 1

    # Only non-multipack ledger lines fall through to the strict H&S write-off.
    if not _ledger_is_shrink_wrapped_multipack(ledger_data):
        return _apply_health_and_safety_writeoff(
            payload,
            ledger_data,
            status_code="DAMAGED",
            format_alert=f"Damage Alerted! {damaged_qty} damaged units recorded.",
        )

    status_code = "FORMAT_VIOLATION_TORN_PACK"
    inner_pack_size = max(1, int(ledger_data.pack_quantity))
    format_alert = (
        f"Torn Multipack Detected! Case of {inner_pack_size} broken — "
        "pro-rata single-unit markdown applies."
    )
    shop_floor_action = "DISPATCH_COLLEAGUE: Remove loose units & attach markdown label."

    # Pro-rata math is always retail_price ÷ case size (pack_quantity), never loose_units_visible.
    multipack_retail = ledger_data.retail_price
    proportional_unit_price = round(multipack_retail / inner_pack_size, 2)
    math_display = (
        f"£{multipack_retail:.2f} ÷ {inner_pack_size} units = £{proportional_unit_price:.2f}"
    )

    if ledger_data.is_alcohol:
        if payload.store_region == "WAL":
            legal_floor = MUP_RATE_PER_UNIT * ledger_data.abv_strength * ledger_data.volume_litres
            rule_applied = f"WALES_MUP_FLOOR (£{legal_floor:.2f}) [Math: {math_display}]"
        elif payload.store_region == "SCO":
            legal_floor = MUP_RATE_PER_UNIT * ledger_data.abv_strength * ledger_data.volume_litres
            rule_applied = f"SCOTLAND_MUP_FLOOR (£{legal_floor:.2f}) [Math: {math_display}]"
        else:
            legal_floor = ledger_data.excise_duty + ledger_data.vat_amount
            rule_applied = f"ENG_DUTY_VAT_FLOOR (£{legal_floor:.2f}) [Math: {math_display}]"

        final_unit_price = max(proportional_unit_price, round(legal_floor, 2))
    else:
        final_unit_price = round(proportional_unit_price, 2)
        rule_applied = f"STANDARD_PROPORTIONAL [Math: {math_display}]"

    transaction_payload = TransactionEnginePayload(
        transaction_type="BOM_DECOMPOSITION_WITH_PRICING",
        reason_code="DAMAGED_FORMAT_PROPORTIONAL_SPLIT",
        ledger_adjustments={
            payload.parent_sku: -1,
            ledger_data.linked_child_sku + "-WASTE": payload.loose_units_visible,
        },
        calculated_unit_price=final_unit_price,
        compliance_rule_applied=rule_applied,
    )

    label_task = LabelPrintPayload(
        printer_target=payload.printer_target
        or f"{payload.physical_location}-ZPL-PRINTER",
        barcode_format="CODE128",
        encoded_sku=ledger_data.linked_child_sku,
        item_trace_id=audit_trace_id,
        price_override_instruction=(
            f"SINGLE_UNIT_LABEL: £{final_unit_price:.2f} ({rule_applied})"
        ),
    )
    return status_code, format_alert, shop_floor_action, transaction_payload, label_task


def _shelf_reconciliation_from_log(row: dict) -> ShelfReconciliation:
    nested = row.get("payload")
    if isinstance(nested, dict) and nested.get("trace_id"):
        cached = ShelfReconciliation(**nested)
        if not cached.product_name:  # rows logged before product names were attached
            cached.product_name = resolve_product_name(cached.ean, cached.sku)
        if cached.case_size is None:
            cached.case_size = resolve_case_size(cached.ean, cached.sku)
        return cached
    return ShelfReconciliation(
        trace_id=str(row["trace_id"]),
        sku=str(row["sku"]),
        ean=str(row.get("ean") or ""),
        product_name=resolve_product_name(row.get("ean"), row.get("sku")),
        case_size=resolve_case_size(row.get("ean"), row.get("sku")),
        status=str(row["status"]),
        format_alert=str(row.get("format_alert") or ""),
        shop_floor_action=str(row.get("shop_floor_action") or ""),
    )


def _parse_damage_event_timestamp(raw: Optional[str]) -> datetime:
    if raw and str(raw).strip():
        text = str(raw).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="timestamp must be ISO-8601 when provided.",
            ) from exc
    return datetime.now(timezone.utc)


def _damage_event_to_cv_detection(
    payload: DamageEventPayload, trx_id: str
) -> CVEdgeDetection:
    stock_name = payload.item_name
    printer_target: Optional[str] = None
    resolved = resolve_cv_catalog_item(stock_name)
    if resolved:
        _, cv_item = resolved
        ean = str(cv_item["ean"])
        parent_sku = parent_sku_for_ean(ean)
        bom_units = max(1, int(cv_item["pack_size"])) * 2
        fixture_id = str(cv_item.get("planogram_location", "CAM-AISLE-04"))
        printer_target = f"{fixture_id}-ZPL-PRINTER"
        product_name = cv_item["name"]
    else:
        catalog_row = catalog_by_product_name().get(stock_name.strip())
        if not catalog_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown shelf item: {stock_name}",
            )
        ean = str(catalog_row["ean"])
        parent_sku = parent_sku_for_ean(ean)
        bom_units = int(catalog_row["bom_units"])
        fixture_id = "CAM-AISLE-04"
        product_name = stock_name

    condition = payload.condition.strip().upper()

    exception_type: Optional[str] = None
    # Provisional value; INTACT is aligned to the ledger's expected_format below.
    detected_format = "SHRINK_WRAPPED_MULTIPACK"
    model_loose = max(0, int(payload.loose_units_visible or 0))
    loose_units_visible = 0

    condition = effective_damage_condition(condition, model_loose)

    if condition == "TORN_MULTIPACK":
        exception_type = "TORN_MULTIPACK"
        detected_format = "TORN_MULTIPACK"
        loose_units_visible = model_loose
    elif condition == "CRUSHED":
        exception_type = "TORN_MULTIPACK"
        detected_format = "TORN_MULTIPACK"
        loose_units_visible = model_loose
    elif condition == "INTACT":
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported condition: {payload.condition}",
        )

    detection = CVEdgeDetection(
        store_region="ENG",
        parent_sku=parent_sku,
        detected_quantity=bom_units,
        physical_location=fixture_id,
        detected_format=detected_format,
        loose_units_visible=loose_units_visible,
        timestamp=_parse_damage_event_timestamp(payload.timestamp),
        confidence_score=payload.confidence_score,
        ean=ean,
        edge_trace_id=trx_id,
        exception_type=exception_type,
        fixture_id=fixture_id,
        product_name=product_name,
        printer_target=printer_target,
    )

    if condition == "INTACT":
        # A healthy item is presented exactly as the ledger expects (single or multipack),
        # so it never trips a false FORMAT_VIOLATION_GENERAL.
        ledger_data = _resolve_ledger(detection)
        detection = detection.model_copy(
            update={"detected_format": ledger_data.expected_format}
        )

    return detection


def process_damage_event(payload: DamageEventPayload) -> ShelfReconciliation:
    """
    Ingest a simplified edge damage event: idempotent on trx_id, then CV bouncer pipeline.
    """
    trx_id = (
        payload.trx_id.strip()
        if payload.trx_id and payload.trx_id.strip()
        else f"TRX-CV-{uuid.uuid4().hex[:12].upper()}"
    )
    cached = get_reconciliation_by_trace_id(trx_id)
    if cached:
        return _shelf_reconciliation_from_log(cached)

    cv_payload = _damage_event_to_cv_detection(payload, trx_id)
    return process_cv_detection(cv_payload)


def process_cv_detection(payload: CVEdgeDetection) -> ShelfReconciliation:
    audit_trace_id = payload.edge_trace_id or f"TRX-{uuid.uuid4().hex[:8].upper()}"
    if payload.edge_trace_id:
        cached = get_reconciliation_by_trace_id(audit_trace_id)
        if cached:
            return _shelf_reconciliation_from_log(cached)

    ledger_data = _resolve_ledger(payload)

    min_confidence = _min_confidence_for_detection(payload, ledger_data)
    if payload.confidence_score < min_confidence:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CV confidence too low.",
        )

    format_alert = "PASS - Clean fill verified"
    status_code = "SYNCED"
    shop_floor_action = "NONE - Inventory aligned"
    transaction_payload: Optional[TransactionEnginePayload] = None
    label_task: Optional[LabelPrintPayload] = None
    exception_type = payload.exception_type or ""

    if exception_type == "ABANDONED_FLATTOP":
        location = payload.fixture_id or payload.physical_location
        product_label = payload.product_name or payload.parent_sku
        status_code = "FORMAT_VIOLATION_ABANDONED_FLATTOP"
        format_alert = (
            f"Abandoned promotional flattop stock: {product_label} left on {location}."
        )
        shop_floor_action = (
            "DISPATCH_COLLEAGUE: Clear abandoned promo presentation and reset flattop planogram."
        )
        transaction_payload = TransactionEnginePayload(
            transaction_type="PROMO_FLATTOP_ABANDONMENT",
            reason_code="ABANDONED_FLATTOP_DETECTED",
            ledger_adjustments={payload.parent_sku: -int(payload.detected_quantity)},
        )

    elif exception_type == "PLANOGRAM_MISMATCH":
        expected_ledger = _ledger_for_ean(payload.expected_ean) if payload.expected_ean else None
        expected_label = (
            expected_ledger.parent_sku if expected_ledger else payload.expected_ean or "UNKNOWN"
        )
        actual_label = payload.product_name or payload.parent_sku
        lost = int(payload.units_lost)
        status_code = "FORMAT_VIOLATION_PLANOGRAM_MISMATCH"
        format_alert = (
            f"Planogram mismatch: slot expected {expected_label}, detected {actual_label}."
        )
        if lost > 0:
            format_alert += f" Shrink signal: {lost} unit(s) unaccounted."
        shop_floor_action = (
            "DISPATCH_COLLEAGUE: Swap to correct SKU and reconcile phantom inventory."
        )
        adjustments: dict[str, int] = {payload.parent_sku: int(payload.detected_quantity)}
        if expected_ledger and expected_ledger.parent_sku != payload.parent_sku:
            adjustments[expected_ledger.parent_sku] = -int(payload.detected_quantity)
        if lost > 0:
            adjustments[payload.parent_sku + "-SHRINK"] = lost
        transaction_payload = TransactionEnginePayload(
            transaction_type="PLANOGRAM_CORRECTION",
            reason_code="SLOT_SKU_MISMATCH",
            ledger_adjustments=adjustments,
        )

    elif _is_torn_multipack_detection(payload, ledger_data) or exception_type == "TORN_MULTIPACK":
        (
            status_code,
            format_alert,
            shop_floor_action,
            transaction_payload,
            label_task,
        ) = _apply_torn_multipack_violation(payload, ledger_data, audit_trace_id)

    elif payload.detected_format != ledger_data.expected_format:
        status_code = "FORMAT_VIOLATION_GENERAL"
        format_alert = (
            f"Expected {ledger_data.expected_format}, found {payload.detected_format}."
        )
        shop_floor_action = "DISPATCH_COLLEAGUE: Correct presentation format."

    result = ShelfReconciliation(
        trace_id=audit_trace_id,
        sku=payload.parent_sku,
        ean=ledger_data.ean,
        product_name=payload.product_name
        or resolve_product_name(ledger_data.ean, payload.parent_sku),
        case_size=max(1, int(ledger_data.pack_quantity)),
        status=status_code,
        format_alert=format_alert,
        shop_floor_action=shop_floor_action,
        transaction_engine_hook=transaction_payload,
        label_print_task=label_task,
    )
    record_reconciliation(
        trace_id=result.trace_id,
        sku=result.sku,
        ean=result.ean,
        status=result.status,
        format_alert=result.format_alert,
        shop_floor_action=result.shop_floor_action,
        payload=result.model_dump(mode="json"),
    )
    return result
