import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from models.bouncer_schemas import (
    BouncerHealthResponse,
    BouncerRejectionItem,
    CVEdgeDetection,
    ShelfReconciliation,
)
from services.api_bouncer_engine import (
    CV_MIN_CONFIDENCE_DAMAGE,
    CV_MIN_CONFIDENCE_INTACT,
    process_cv_detection,
)
from services.product_lookup import resolve_case_size, resolve_product_name
from services.edge_feed import (
    latest_frame,
    list_feed_events,
    purge_feed,
    summarize_feed,
)
from services.bouncer_buffer import (
    BOUNCER_DB_PATH,
    count_rejections_since,
    list_reconciliations,
    list_rejections,
    purge_reconciliation_log,
)
from services.waste_metrics import reset_daily_waste_totals

router = APIRouter(prefix="/api/v1/bouncer", tags=["api-bouncer"])


@router.post("/cv-detection", response_model=ShelfReconciliation)
def ingest_cv_detection(payload: CVEdgeDetection):
    """Edge CV webhook (token validated in ApiBouncerMiddleware)."""
    return process_cv_detection(payload)


@router.get("/health", response_model=BouncerHealthResponse)
def bouncer_health():
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    reconciliations = list_reconciliations(limit=500)
    return BouncerHealthResponse(
        status="ok",
        edge_token_configured=bool(os.getenv("BOUNCER_EDGE_TOKEN", "edge-cam-prod-992-xtz")),
        rate_limit_per_minute=int(os.getenv("BOUNCER_CV_RATE_LIMIT_PER_MINUTE", "30")),
        fill_rate_limit_per_minute=int(os.getenv("BOUNCER_FILL_RATE_LIMIT_PER_MINUTE", "120")),
        max_body_bytes=int(os.getenv("BOUNCER_MAX_BODY_BYTES", "65536")),
        rejections_last_hour=count_rejections_since(since),
        reconciliations_total=len(reconciliations),
        wal_buffer_path=BOUNCER_DB_PATH,
    )


@router.get("/rejections", response_model=list[BouncerRejectionItem])
def active_rejections(limit: int = 50):
    rows = list_rejections(limit=limit)
    return [BouncerRejectionItem(**row) for row in rows]


@router.get("/reconciliations")
def reconciliation_logs(limit: int = 50):
    rows = list_reconciliations(limit=limit)
    for row in rows:
        # Older rows were logged before product names were attached; resolve them on read.
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        name = (
            payload.get("product_name")
            or resolve_product_name(row.get("ean"), row.get("sku"))
        )
        case_size = payload.get("case_size") or resolve_case_size(
            row.get("ean"), row.get("sku")
        )
        row["product_name"] = name
        row["case_size"] = case_size
        if isinstance(row.get("payload"), dict):
            if name and not row["payload"].get("product_name"):
                row["payload"]["product_name"] = name
            if case_size and not row["payload"].get("case_size"):
                row["payload"]["case_size"] = case_size
    return rows


@router.get("/edge-feed")
def edge_feed(limit: int = 25):
    """Live edge_camera.py telemetry: confidence, thresholds, case size and routing per capture."""
    events = list_feed_events(limit=limit)
    return {
        "summary": summarize_feed(events),
        "events": events,
        "confidence_floors": {
            "intact": CV_MIN_CONFIDENCE_INTACT,
            "damage": CV_MIN_CONFIDENCE_DAMAGE,
        },
        "latest_frame": latest_frame(),
    }


@router.delete("/edge-feed")
def purge_edge_feed():
    return {"status": "ok", "deleted": purge_feed()}


@router.delete("/purge")
def purge_reconciliation_ledger():
    """Wipe all CV reconciliation rows from the SQLite WAL buffer."""
    deleted = purge_reconciliation_log()
    reset_daily_waste_totals()
    return {"status": "ok", "deleted": deleted}
