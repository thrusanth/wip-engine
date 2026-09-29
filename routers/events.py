from fastapi import APIRouter, Depends, HTTPException
from models.schemas import ResolutionEvent, TelemetryResponse
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