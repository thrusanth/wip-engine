from fastapi import APIRouter
from models.schemas import TelemetryResponse
from services.engine import engine

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])

@router.get("", response_model=TelemetryResponse)
def get_telemetry():
    """Returns global metrics and the state of all active containers."""
    return engine.get_telemetry()