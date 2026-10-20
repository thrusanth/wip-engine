import logging

from fastapi import APIRouter, HTTPException, status

from models.bouncer_schemas import DamageEventPayload, DamageEventResponse
from services.api_bouncer_engine import process_damage_event

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
    try:
        reconciliation = process_damage_event(payload)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to process CV damage event for item=%s", payload.item_name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing damage event.",
        ) from None

    return DamageEventResponse(
        trx_id=reconciliation.trace_id,
        transaction_status=reconciliation.status,
        reconciliation=reconciliation,
    )
