from fastapi import APIRouter, HTTPException
from models.schemas import ResolutionEvent, TelemetryResponse
from services.engine import engine

router = APIRouter(prefix="/api/v1/events", tags=["events"])

@router.post("/resolve", response_model=TelemetryResponse)
def resolve_event(event: ResolutionEvent):
    """Processes a resolution event submitted by a Shift Leader."""
    try:
        return engine.resolve_event(event)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))