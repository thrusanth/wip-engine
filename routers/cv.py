import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from models.bouncer_schemas import (
    DamageEventPayload,
    DamageEventResponse,
    FrameAnalyzePayload,
)
from services.api_bouncer_engine import (
    confidence_floor_for_condition,
    effective_damage_condition,
    process_damage_event,
)
from services.cv_catalog import expected_ledger_from_cv_item, resolve_cv_catalog_item
from services.edge_feed import (
    ROUTING_REJECTED,
    make_thumbnail_b64,
    record_feed_event,
    routing_from_result,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cv", tags=["cv-ingestion"])


def _record_feed(
    *,
    payload: DamageEventPayload,
    catalog_key: Optional[str],
    item: Optional[dict],
    reconciliation=None,
    error: Optional[HTTPException] = None,
) -> None:
    """Best-effort live-feed telemetry; never blocks or fails CV ingestion."""
    try:
        raw_condition = payload.condition.strip().upper()
        effective = effective_damage_condition(raw_condition, payload.loose_units_visible)
        threshold = confidence_floor_for_condition(effective)
        case_size = max(1, int(item["pack_size"])) if item else None
        expected_format = None
        if item:
            expected_format = expected_ledger_from_cv_item(item).expected_format

        hook = getattr(reconciliation, "transaction_engine_hook", None)
        rejected = error is not None
        routing = routing_from_result(
            status=reconciliation.status if reconciliation else "",
            transaction_type=hook.transaction_type if hook else None,
            rejected=rejected,
        )
        record_feed_event(
            source=payload.source or "edge_camera",
            catalog_key=catalog_key,
            item_name=item["name"] if item else payload.item_name,
            raw_condition=raw_condition,
            effective_condition=effective,
            confidence_score=payload.confidence_score,
            confidence_threshold=threshold,
            case_size=case_size,
            expected_format=expected_format,
            routing=routing,
            status=(
                f"HTTP_{error.status_code}" if error else reconciliation.status
            ),
            detail=str(error.detail) if error else None,
            calculated_unit_price=hook.calculated_unit_price if hook else None,
            label_printed=bool(
                reconciliation and reconciliation.label_print_task
            ),
            frame_b64=payload.frame_thumbnail_b64,
            trace_id=reconciliation.trace_id if reconciliation else payload.trx_id,
        )
    except Exception:  # noqa: BLE001 - telemetry must not break ingestion
        logger.exception("Failed to record edge feed event")


def _ingest(payload: DamageEventPayload) -> DamageEventResponse:
    resolved = resolve_cv_catalog_item(payload.item_name)
    if not resolved:
        error = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown CV catalog item: {payload.item_name}",
        )
        _record_feed(payload=payload, catalog_key=None, item=None, error=error)
        raise error
    catalog_key, item = resolved

    catalog_payload = DamageEventPayload(
        item_name=item["name"],
        condition=payload.condition,
        confidence_score=payload.confidence_score,
        loose_units_visible=payload.loose_units_visible,
        trx_id=payload.trx_id,
        timestamp=payload.timestamp,
    )

    try:
        reconciliation = process_damage_event(catalog_payload)
    except HTTPException as exc:
        _record_feed(payload=payload, catalog_key=catalog_key, item=item, error=exc)
        raise
    except Exception:
        logger.exception(
            "Failed to process CV damage event for item=%s", item["name"]
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing damage event.",
        ) from None

    _record_feed(
        payload=payload,
        catalog_key=catalog_key,
        item=item,
        reconciliation=reconciliation,
    )
    return DamageEventResponse(
        trx_id=reconciliation.trace_id,
        transaction_status=reconciliation.status,
        reconciliation=reconciliation,
    )


@router.post(
    "/damage-event",
    response_model=DamageEventResponse,
    status_code=status.HTTP_200_OK,
)
def ingest_damage_event(payload: DamageEventPayload) -> DamageEventResponse:
    """
    Edge camera damage webhook — idempotent on trx_id, WAL reconciliation ledger.
    """
    return _ingest(payload)


@router.post("/analyze-frame", status_code=status.HTTP_200_OK)
def analyze_frame(payload: FrameAnalyzePayload) -> dict:
    """
    Classify a camera frame with Luna (same pipeline as edge_camera.py), then route it
    through the API Bouncer. Always answers 200 with the decision + routing outcome so
    the dashboard can render rejected captures too.
    """
    import edge_camera  # lazy: keeps backend import light, shares the Luna prompt/parsing

    try:
        thumbnail = make_thumbnail_b64(payload.image_b64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unreadable image frame: {exc}",
        ) from exc

    try:
        decision = edge_camera.evaluate_damage_with_luna(thumbnail)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Luna returned an unusable classification: {exc}",
        ) from exc

    event = DamageEventPayload(
        item_name=str(decision["catalog_key"]),
        condition=str(decision["condition"]),
        confidence_score=float(decision["confidence"]),
        loose_units_visible=int(decision.get("loose_units_visible", 0)),
        source=payload.source or "dashboard_camera",
        frame_thumbnail_b64=thumbnail,
    )
    try:
        result = _ingest(event)
    except HTTPException as exc:
        return {
            "decision": decision,
            "routing": ROUTING_REJECTED,
            "http_status": exc.status_code,
            "detail": exc.detail,
            "reconciliation": None,
        }
    return {
        "decision": decision,
        "routing": result.transaction_status,
        "http_status": 200,
        "detail": None,
        "reconciliation": result.reconciliation.model_dump(),
    }
