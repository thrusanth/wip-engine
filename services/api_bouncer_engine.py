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

MUP_RATE_PER_UNIT = float(os.getenv("BOUNCER_MUP_RATE_PER_UNIT", "0.65"))

CENTRAL_LEDGER_DB: dict[str, ExpectedLedger] = {
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


def process_cv_detection(payload: CVEdgeDetection) -> ShelfReconciliation:
    if payload.confidence_score < 0.85:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CV confidence too low.",
        )

    ledger_data = CENTRAL_LEDGER_DB.get(payload.parent_sku)
    if not ledger_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found.")

    format_alert = "PASS - Clean fill verified"
    status_code = "SYNCED"
    shop_floor_action = "NONE - Inventory aligned"
    transaction_payload: Optional[TransactionEnginePayload] = None
    label_task: Optional[LabelPrintPayload] = None
    audit_trace_id = f"TRX-{uuid.uuid4().hex[:8].upper()}"

    if payload.detected_format != ledger_data.expected_format:
        if payload.detected_format == "TORN_MULTIPACK" and payload.loose_units_visible > 0:
            status_code = "FORMAT_VIOLATION_TORN_PACK"
            format_alert = (
                f"Torn Multipack Detected! {payload.loose_units_visible} loose units exposed."
            )
            shop_floor_action = (
                "DISPATCH_COLLEAGUE: Remove loose units & attach markdown label."
            )

            proportional_unit_price = ledger_data.retail_price / ledger_data.pack_quantity
            math_display = (
                f"£{ledger_data.retail_price:.2f} ÷ {ledger_data.pack_quantity} units "
                f"= £{proportional_unit_price:.2f}"
            )

            if ledger_data.is_alcohol:
                if payload.store_region == "WAL":
                    legal_floor = (
                        MUP_RATE_PER_UNIT * ledger_data.abv_strength * ledger_data.volume_litres
                    )
                    rule_applied = (
                        f"WALES_MUP_FLOOR (£{legal_floor:.2f}) [Math: {math_display}]"
                    )
                elif payload.store_region == "SCO":
                    legal_floor = (
                        MUP_RATE_PER_UNIT * ledger_data.abv_strength * ledger_data.volume_litres
                    )
                    rule_applied = (
                        f"SCOTLAND_MUP_FLOOR (£{legal_floor:.2f}) [Math: {math_display}]"
                    )
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
        else:
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
