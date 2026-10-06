from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, field_validator
from uuid import uuid4

# ---------------------------------------------------------
# Enums
# ---------------------------------------------------------
class ContainerStatus(str, Enum):
    """Status of the physical container."""
    STAGED_IN_BACKROOM = "STAGED_IN_BACKROOM"
    IN_PROGRESS_SHOPFLOOR = "IN_PROGRESS_SHOPFLOOR"
    ABANDONED_MID_SHIFT = "ABANDONED_MID_SHIFT"
    SHIFT_ROLLOVER = "SHIFT_ROLLOVER"
    RETURNED_MIXED = "RETURNED_MIXED"

class ResolutionType(str, Enum):
    """The type of resolution applied by a shift leader."""
    ALL = "all"
    NONE = "none"
    PARTIAL = "partial"


class ExceptionKind(str, Enum):
    """Category of live inventory execution anomaly."""
    PHANTOM_DRIFT = "phantom_drift"
    CAGE_DISCREPANCY = "cage_discrepancy"
    SKU_VARIANCE = "sku_variance"
    UNTRACKED_BACKSTOCK = "untracked_backstock"
    TOTAL_POWER_CUT = "total_power_cut"


TOTAL_POWER_CUT_STATUS = "Mandatory Full Gap Scan Required"

# ---------------------------------------------------------
# Core Domain Models
# ---------------------------------------------------------
def _validate_ean13(value: str) -> str:
    if len(value) != 13 or not value.isdigit():
        raise ValueError("EAN must be a 13-digit numeric barcode")
    return value


class SkuState(BaseModel):
    """The state of a specific SKU within a container."""
    sku: str
    name: str = ""
    ean: str = ""
    expected: int
    worked: int = 0
    backstock: int = 0
    confirmed_backstock: int = 0
    cv_filled: int = 0
    price: Optional[float] = None

    # Computed fields (these will be enriched by the engine before returning)
    drift: int = 0
    variance: int = 0
    is_resolved: bool = False
    resolution_type: Optional[ResolutionType] = None
    recovered_units: int = 0
    shrink_confirmed: int = 0

    @field_validator("ean")
    @classmethod
    def validate_ean(cls, value: str) -> str:
        if not value:
            return value
        return _validate_ean13(value)


class ContainerState(BaseModel):
    """The overall state of a physical container on the shop floor."""
    id: str
    status: ContainerStatus
    zone: str
    skus: List[SkuState]
    is_pending: bool = False


class ActiveException(BaseModel):
    """A live exception surfaced by telemetry or the background simulator."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: ExceptionKind
    container_id: str
    sku: str
    ean: str = ""
    zone: str
    units: int = Field(..., ge=0)
    message: str
    status: str = ""
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("ean")
    @classmethod
    def validate_ean(cls, value: str) -> str:
        if not value:
            return value
        return _validate_ean13(value)


# ---------------------------------------------------------
# Event Models (Input)
# ---------------------------------------------------------
class ResolutionEvent(BaseModel):
    """Payload received from the frontend when a shift leader resolves a variance."""
    container_id: str
    sku: str
    resolution_type: ResolutionType
    recovered_units: int = 0

class FillTelemetryEvent(BaseModel):
    """Payload from edge clients when a shelf fill / POS decrement is observed."""
    event_id: str
    sku: str
    action: str = "decrement"
    timestamp: str


class OfflineFillAuditEntry(BaseModel):
    """Central ledger record for edge-buffer fills replayed after connectivity returns."""
    event_id: str
    sku: str
    name: str = ""
    quantity: int = Field(default=1, ge=1)
    action: str
    timestamp: str
    sync_status: str = "Synced / Offline Fill"


class DeliveryManifestLine(BaseModel):
    sku: str
    expected_units: int = Field(..., ge=1)


class IncomingDeliveryManifest(BaseModel):
    manifest_id: str
    zone: str = "Backroom Staging"
    lines: List[DeliveryManifestLine]


class TotalPowerCutEvent(BaseModel):
    manifest_id: str
    timestamp: str


class ManifestAutoConfirmEntry(BaseModel):
    """Central ledger row when a pending delivery manifest is auto-confirmed after power loss."""
    manifest_id: str
    sku: str
    name: str = ""
    expected_units: int
    confirmed_units: int
    timestamp: str
    sync_status: str = "Auto-Confirmed / Total Power Cut"


class OfflinePartialFillReport(BaseModel):
    """Post-blackout reconciliation when shelf fills do not match case manifest."""
    batch_id: str
    sku: str
    expected_units: int = Field(..., ge=1)
    recorded_shelf_units: int = Field(..., ge=0)
    action: str = "fill"
    timestamp: str


class InventoryGapAuditEntry(BaseModel):
    """Ledger row for unlogged backstock / gap-scan exceptions after partial offline fills."""
    batch_id: str
    sku: str
    name: str = ""
    expected_units: int
    recorded_units: int
    variance_delta: int
    unlogged_backstock_units: int
    action: str
    timestamp: str
    status: str = "Gap Scan Recommended"


class SKUVisualSignature(BaseModel):
    """Localized visual feature row cached on the edge after a cloud teach pass."""

    sku_id: str
    ean: str = ""
    feature_hash: str
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)


class OfflineDetectionEvent(BaseModel):
    """Append-only edge detection emitted while the camera runs in disconnected autonomy."""

    timestamp: str
    sku_id: str
    detected_quantity: int = Field(..., ge=0)
    status: str = "[STATE: DISCONNECTED_AUTONOMY]"


# ---------------------------------------------------------
# Metrics Models (Output)
# ---------------------------------------------------------
class GlobalMetrics(BaseModel):
    """Top-level metrics representing the state of the entire system."""
    pending_delivery_cages: int = 4
    active_flattops: int = 3
    detected_phantom_drift: int = 0
    daily_shrink_cost: float = 0.0
    pending_edge_tasks: int = 0

class TelemetryResponse(BaseModel):
    """The full payload returned to the frontend."""
    metrics: GlobalMetrics
    containers: Dict[str, ContainerState]
    active_exceptions: List[ActiveException] = Field(default_factory=list)
    offline_fill_audit: List[OfflineFillAuditEntry] = Field(default_factory=list)
    inventory_gap_audit: List[InventoryGapAuditEntry] = Field(default_factory=list)
    manifest_auto_confirm_audit: List[ManifestAutoConfirmEntry] = Field(default_factory=list)