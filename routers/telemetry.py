from fastapi import APIRouter
from models.schemas import FillTelemetryEvent, TelemetryResponse
from services.engine import engine

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])

FILL_ROUTE = "/fill"


@router.get("", response_model=TelemetryResponse)
def get_telemetry():
    """Returns global metrics and the state of all active containers."""
    return engine.get_telemetry()


@router.post(FILL_ROUTE, response_model=TelemetryResponse)
def ingest_fill_event(event: FillTelemetryEvent):
    """Ingests edge fill telemetry (idempotent on event_id)."""
    return engine.process_fill_event(event)