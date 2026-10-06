from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

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

# ---------------------------------------------------------
# Core Domain Models
# ---------------------------------------------------------
class SkuState(BaseModel):
    """The state of a specific SKU within a container."""
    sku: str
    expected: int
    worked: int = 0
    backstock: int = 0
    confirmed_backstock: int = 0
    cv_filled: int = 0
    
    # Computed fields (these will be enriched by the engine before returning)
    drift: int = 0
    variance: int = 0
    is_resolved: bool = False
    resolution_type: Optional[ResolutionType] = None
    recovered_units: int = 0
    shrink_confirmed: int = 0

class ContainerState(BaseModel):
    """The overall state of a physical container on the shop floor."""
    id: str
    status: ContainerStatus
    zone: str
    skus: List[SkuState]
    is_pending: bool = False

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