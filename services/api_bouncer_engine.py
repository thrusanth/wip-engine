"""CV format violation interceptor and shelf reconciliation (migrated from api_bouncer)."""

from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import HTTPException, status

from models.bouncer_schemas import (
    CVEdgeDetection,
    ExpectedLedger,
    LabelPrintPayload,
    ShelfReconciliation,
    TransactionEnginePayload,
)
from services.bouncer_buffer import record_reconciliation
from services.waste_metrics import record_scenario_a_waste
from services.shopfloor_catalog import (
    build_master_ledger_db,
    catalog_by_ean,
    parent_sku_for_ean,
)

MUP_RATE_PER_UNIT = float(os.getenv("BOUNCER_MUP_RATE_PER_UNIT", "0.65"))

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
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found.")


def _ledger_for_ean(ean: str) -> Optional[ExpectedLedger]:
    return CENTRAL_LEDGER_DB.get(parent_sku_for_ean(ean))


def _torn_routing_product_name(
    payload: CVEdgeDetection,
    ledger_data: ExpectedLedger,
) -> str:
    if payload.product_name and str(payload.product_name).strip():
        return str(payload.product_name).strip()
    catalog_row = catalog_by_ean().get(ledger_data.ean)
    if catalog_row:
        return str(catalog_row["product_name"])
    return ledger_data.parent_sku


def _apply_health_and_safety_writeoff(
    payload: CVEdgeDetection,
    ledger_data: ExpectedLedger,
    *,
    status_code: str,
    format_alert: str,
) -> tuple[str, str, str, TransactionEnginePayload, None]:
    damaged_qty = int(payload.loose_units_visible)
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
    status_code = "FORMAT_VIOLATION_TORN_PACK"
    format_alert = (
        f"Torn Multipack Detected! {payload.loose_units_visible} loose units exposed."
    )
    shop_floor_action = "DISPATCH_COLLEAGUE: Remove loose units & attach markdown label."

    product_name = _torn_routing_product_name(payload, ledger_data)
    is_master_ean_sku = ledger_data.parent_sku.startswith("EAN-")
    if is_master_ean_sku and "multipack" not in product_name.lower():
        return _apply_health_and_safety_writeoff(
            payload,
            ledger_data,
            status_code=status_code,
            format_alert=format_alert,
        )

    multipack_retail = ledger_data.retail_price
    inner_pack_size = ledger_data.pack_quantity
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
        printer_target=f"{payload.physical_location}-ZPL-PRINTER",
        barcode_format="CODE128",
        encoded_sku=ledger_data.linked_child_sku,
        item_trace_id=audit_trace_id,
        price_override_instruction=(
            f"SINGLE_UNIT_LABEL: £{final_unit_price:.2f} ({rule_applied})"
        ),
    )
    return status_code, format_alert, shop_floor_action, transaction_payload, label_task


def process_cv_detection(payload: CVEdgeDetection) -> ShelfReconciliation:
    if payload.confidence_score < 0.85:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CV confidence too low.",
        )

    ledger_data = _resolve_ledger(payload)

    format_alert = "PASS - Clean fill verified"
    status_code = "SYNCED"
    shop_floor_action = "NONE - Inventory aligned"
    transaction_payload: Optional[TransactionEnginePayload] = None
    label_task: Optional[LabelPrintPayload] = None
    audit_trace_id = payload.edge_trace_id or f"TRX-{uuid.uuid4().hex[:8].upper()}"
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

    elif exception_type == "TORN_MULTIPACK" or (
        payload.detected_format != ledger_data.expected_format
        and payload.detected_format == "TORN_MULTIPACK"
        and payload.loose_units_visible > 0
    ):
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
