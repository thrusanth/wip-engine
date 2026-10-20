import logging

from fastapi import APIRouter, HTTPException, status

from models.bouncer_schemas import DamageEventPayload, DamageEventResponse
from services.api_bouncer_engine import process_damage_event
from services.cv_catalog import resolve_cv_catalog_item

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cv", tags=["cv-ingestion"])


@router.post(
    "/damage-event",
    response_model=DamageEventResponse,
    status_code=status.HTTP_200_OK,
)
def ingest_damage_event(payload: DamageEventPayload) -> DamageEventResponse:
    """
    Edge camera damage webhook — idempotent on trx_id, WAL reconciliation ledger.
    """
    resolved = resolve_cv_catalog_item(payload.item_name)
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown CV catalog item: {payload.item_name}",
        )
    _, item = resolved

    catalog_payload = DamageEventPayload(
        item_name=item["name"],
        condition=payload.condition,
        confidence_score=payload.confidence_score,
        trx_id=payload.trx_id,
        timestamp=payload.timestamp,
    )

    try:
        reconciliation = process_damage_event(catalog_payload)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to process CV damage event for item=%s", item["name"]
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing damage event.",
        ) from None

    return DamageEventResponse(
        trx_id=reconciliation.trace_id,
        transaction_status=reconciliation.status,
        reconciliation=reconciliation,
    )
