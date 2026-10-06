from fastapi import APIRouter, Depends, HTTPException
from models.schemas import (
    IncomingDeliveryManifest,
    ResolutionEvent,
    TelemetryResponse,
    TotalPowerCutEvent,
)
from security import require_api_key
from services.engine import engine

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post("/resolve", response_model=TelemetryResponse, dependencies=[Depends(require_api_key)])
def resolve_event(event: ResolutionEvent):
    """Processes a resolution event submitted by a Shift Leader."""
    try:
        return engine.resolve_event(event)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/delivery-manifest", response_model=TelemetryResponse)
def stage_delivery_manifest(manifest: IncomingDeliveryManifest):
    """Stage an inbound delivery manifest prior to cage breakdown."""
    try:
        return engine.stage_incoming_delivery_manifest(manifest)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/total-power-cut", response_model=TelemetryResponse)
def trigger_total_power_cut(event: TotalPowerCutEvent):
    """Simulate catastrophic power loss during delivery and auto-confirm manifest."""
    try:
        return engine.apply_total_power_cut(event)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
