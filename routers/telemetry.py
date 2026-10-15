from fastapi import APIRouter, HTTPException
from models.schemas import FillTelemetryEvent, OfflinePartialFillReport, TelemetryResponse
from services.engine import engine
from services.waste_metrics import get_daily_waste_totals

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])

FILL_ROUTE = "/fill"
OFFLINE_PARTIAL_FILL_ROUTE = "/offline-partial-fill"


@router.get("", response_model=TelemetryResponse)
def get_telemetry():
    """Returns global metrics and the state of all active containers."""
    response = engine.get_telemetry()
    waste = get_daily_waste_totals()
    metrics = response.metrics.model_copy(deep=True)
    metrics.daily_waste_qty = int(waste["daily_waste_qty"])
    metrics.daily_waste_cost = float(waste["daily_waste_cost"])
    metrics.daily_shrink_cost = round(
        metrics.daily_shrink_cost + metrics.daily_waste_cost,
        2,
    )
    return response.model_copy(update={"metrics": metrics})


@router.post(FILL_ROUTE, response_model=TelemetryResponse)
def ingest_fill_event(event: FillTelemetryEvent):
    """Ingests edge fill telemetry (idempotent on event_id)."""
    return engine.process_fill_event(event)


@router.post(OFFLINE_PARTIAL_FILL_ROUTE, response_model=TelemetryResponse)
def ingest_offline_partial_fill(report: OfflinePartialFillReport):
    """Reconcile partial offline fills and raise gap-scan exceptions for unlogged units."""
    try:
        return engine.process_offline_partial_fill_gap(report)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc