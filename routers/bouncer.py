import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from models.bouncer_schemas import (
    BouncerHealthResponse,
    BouncerRejectionItem,
    CVEdgeDetection,
    ShelfReconciliation,
)
from services.api_bouncer_engine import process_cv_detection
from services.bouncer_buffer import (
    BOUNCER_DB_PATH,
    count_rejections_since,
    list_reconciliations,
    list_rejections,
)

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
    return list_reconciliations(limit=limit)
