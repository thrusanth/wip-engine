from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class ExpectedLedger(BaseModel):
    parent_sku: str
    ean: str
    expected_quantity: int
    planogram_location: str
    expected_format: str
    linked_child_sku: str
    retail_price: float
    pack_quantity: int
    is_alcohol: bool = False
    abv_strength: Optional[float] = None
    volume_litres: Optional[float] = None
    excise_duty: Optional[float] = None
    vat_amount: Optional[float] = None
    allow_loose_resale: bool = True


class CVEdgeDetection(BaseModel):
    store_region: str = "ENG"
    parent_sku: str
    detected_quantity: int
    physical_location: str
    detected_format: str
    loose_units_visible: int
    timestamp: datetime
    confidence_score: float = Field(ge=0.0, le=1.0)
    ean: Optional[str] = None
    edge_trace_id: Optional[str] = None
    exception_type: Optional[str] = None
    expected_ean: Optional[str] = None
    units_lost: int = 0
    fixture_id: Optional[str] = None
    product_name: Optional[str] = None


class TransactionEnginePayload(BaseModel):
    transaction_type: str
    reason_code: str
    ledger_adjustments: Dict[str, int]
    calculated_unit_price: Optional[float] = None
    compliance_rule_applied: Optional[str] = None
    adjustment_summary: Optional[str] = None


class LabelPrintPayload(BaseModel):
    printer_target: str
    barcode_format: str
    encoded_sku: str
    item_trace_id: str
    price_override_instruction: str


class ShelfReconciliation(BaseModel):
    trace_id: str
    sku: str
    ean: str
    status: str
    format_alert: str
    shop_floor_action: str
    transaction_engine_hook: Optional[TransactionEnginePayload] = None
    label_print_task: Optional[LabelPrintPayload] = None


class BouncerHealthResponse(BaseModel):
    status: str
    edge_token_configured: bool
    rate_limit_per_minute: int
    fill_rate_limit_per_minute: int
    max_body_bytes: int
    rejections_last_hour: int
    reconciliations_total: int
    wal_buffer_path: str


class BouncerRejectionItem(BaseModel):
    id: int
    created_at: str
    client_ip: Optional[str] = None
    path: str
    reason_code: str
    detail: Optional[str] = None
    payload_preview: Optional[str] = None
