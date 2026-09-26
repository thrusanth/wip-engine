from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ContainerState(str, Enum):
    """
    Represents the physical status and location of a mixed-SKU container 
    (flattop/cage) during retail execution to prevent inventory drift.
    """
    STAGED_IN_BACKROOM = "STAGED_IN_BACKROOM"
    IN_PROGRESS_SHOPFLOOR = "IN_PROGRESS_SHOPFLOOR"
    ABANDONED_MID_SHIFT = "ABANDONED_MID_SHIFT"
    SHIFT_ROLLOVER = "SHIFT_ROLLOVER"  # Left unworked for the next day
    RETURNED_MIXED = "RETURNED_MIXED"  # Partial payload pushed back to the warehouse


class ContainerItem(BaseModel):
    """
    Tracks the lifecycle of a specific SKU within a container, accounting for 
    what was expected vs. actual outcomes (worked, backstocked, or abandoned).
    """
    sku: str = Field(..., description="Stock Keeping Unit identifier")
    expected_quantity: int = Field(..., ge=0, description="Quantity initially assigned to this container")
    actual_quantity: int = Field(..., ge=0, description="Quantity physically verified in the container")
    backstock_quantity: int = Field(
        default=0, 
        ge=0, 
        description="Quantity binned directly to overstock backroom locations"
    )
    unworked_returned_quantity: int = Field(
        default=0, 
        ge=0, 
        description="Quantity dumped back into general warehouse areas without being worked or properly binned"
    )


class WipContainer(BaseModel):
    """
    Main entity tracking a physical work-in-progress (WIP) container. 
    Maintains accountability across shift handovers by logging the container's 
    state, location, and detailed SKU payload.
    """
    lpn: str = Field(..., description="License Plate Number (Unique string ID for the container)")
    state: ContainerState = Field(
        default=ContainerState.STAGED_IN_BACKROOM, 
        description="Current operational state of the container"
    )
    assigned_shift_id: Optional[str] = Field(
        default=None, 
        description="ID of the shift responsible for working this container"
    )
    current_zone: str = Field(..., description="Physical location on the shop floor (e.g., 'Aisle 4')")
    items: List[ContainerItem] = Field(
        default_factory=list, 
        description="List of items and their quantities within the container"
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Timestamp of the last state or inventory modification"
    )
