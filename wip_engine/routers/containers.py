from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from models.wip_container import ContainerState, WipContainer

router = APIRouter(prefix="/containers", tags=["containers"])

# In-memory dictionary store for containers
containers_db: Dict[str, WipContainer] = {}

# --- Request & Response Models ---

class StateUpdateRequest(BaseModel):
    """Payload for updating a container's operational state and location."""
    state: ContainerState = Field(..., description="New operational state")
    current_zone: str = Field(..., description="New physical zone/location")


class ReconcileItemCount(BaseModel):
    """Finalized item counts provided during container close-out/audit."""
    sku: str = Field(..., description="SKU identifier")
    actual_quantity: int = Field(..., ge=0, description="Quantity physically verified in the container")
    backstock_quantity: int = Field(..., ge=0, description="Quantity binned to overstock")
    unworked_returned_quantity: int = Field(..., ge=0, description="Quantity returned without being worked")


class ReconcileRequest(BaseModel):
    """Payload containing finalized counts for all SKUs in the container."""
    items: List[ReconcileItemCount]


class SkuDiscrepancy(BaseModel):
    """Detailed reconciliation result for a single SKU."""
    sku: str
    expected_quantity: int
    accounted_quantity: int
    phantom_drift: int
    has_discrepancy: bool


class ReconcileResponse(BaseModel):
    """Response returned after auditing a container, detailing any drift."""
    lpn: str
    discrepancies: List[SkuDiscrepancy]
    total_phantom_drift: int


# --- Endpoints ---

@router.post(
    "",
    response_model=WipContainer,
    status_code=status.HTTP_201_CREATED,
    summary="Register/Stage a new container",
)
def register_container(container: WipContainer):
    """
    Register a new WIP container entering the store.
    Provides the initial manifest of items and sets its initial state.
    """
    if container.lpn in containers_db:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Container with LPN '{container.lpn}' already exists."
        )
    
    containers_db[container.lpn] = container
    return container


@router.patch(
    "/{lpn}/state",
    response_model=WipContainer,
    summary="Update container state",
)
def update_container_state(lpn: str, payload: StateUpdateRequest):
    """
    Update the container state (e.g., IN_PROGRESS_SHOPFLOOR -> ABANDONED_MID_SHIFT)
    and its current zone.
    """
    if lpn not in containers_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Container with LPN '{lpn}' not found."
        )
    
    container = containers_db[lpn]
    container.state = payload.state
    container.current_zone = payload.current_zone
    container.last_updated = datetime.now(timezone.utc)
    
    return container


@router.post(
    "/{lpn}/reconcile",
    response_model=ReconcileResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconcile and close out a container",
)
def reconcile_container(lpn: str, payload: ReconcileRequest):
    """
    Close out or audit a container by accepting finalized counts.
    Computes phantom drift and flags discrepancies if expected counts
    do not align with accounted physical inventory.
    """
    if lpn not in containers_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Container with LPN '{lpn}' not found."
        )
    
    container = containers_db[lpn]
    
    # Create a fast lookup for existing items in the container
    container_items_map = {item.sku: item for item in container.items}
    
    discrepancies = []
    total_drift = 0
    
    for req_item in payload.items:
        if req_item.sku not in container_items_map:
            # Handle case where a SKU is reported but wasn't in the original manifest
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SKU '{req_item.sku}' not found in container manifest."
            )
        
        # Retrieve the original item reference to update it
        c_item = container_items_map[req_item.sku]
        
        # Update container item quantities based on audit
        c_item.actual_quantity = req_item.actual_quantity
        c_item.backstock_quantity = req_item.backstock_quantity
        c_item.unworked_returned_quantity = req_item.unworked_returned_quantity
        
        # In a retail context, accounted inventory is usually what is physically 
        # verified + what was diverted to backstock + what was abandoned/returned.
        # (Assuming the remainder was properly 'worked' to the shelf).
        # Drift indicates missing inventory that was expected but cannot be accounted for.
        accounted_quantity = (
            req_item.actual_quantity + 
            req_item.backstock_quantity + 
            req_item.unworked_returned_quantity
        )
        
        # Expected quantity is the source of truth for what *should* have been there.
        # Phantom drift: we expected X, but can only physically trace Y.
        phantom_drift = c_item.expected_quantity - accounted_quantity
        has_discrepancy = phantom_drift != 0
        
        total_drift += phantom_drift
        
        discrepancies.append(
            SkuDiscrepancy(
                sku=req_item.sku,
                expected_quantity=c_item.expected_quantity,
                accounted_quantity=accounted_quantity,
                phantom_drift=phantom_drift,
                has_discrepancy=has_discrepancy
            )
        )
        
    container.last_updated = datetime.now(timezone.utc)
    
    return ReconcileResponse(
        lpn=lpn,
        discrepancies=discrepancies,
        total_phantom_drift=total_drift
    )
