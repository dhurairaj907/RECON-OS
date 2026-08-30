"""
RECON OS — Simulator Router

Endpoints for triggering simulated payment events during development and demos.
Feeds through the exact same database and event processing pipeline.

The simulator is NOT part of the real recovery path. It is disabled by default
(RECON_SIMULATOR_ENABLED=false) and, when enabled, every record and audit entry
it produces is stamped simulated=true.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import settings
from database import get_db, seed_default_merchant
from schemas.simulator import (
    SimulateEventRequest,
    SimulateEventResponse,
    SimulatePaymentLinkPaidRequest,
)
from services.simulator_service import simulate_event, simulate_payment_link_paid

logger = logging.getLogger("recon.routers.simulator")
router = APIRouter(prefix="/simulator", tags=["Simulator"])


def _require_simulator_enabled():
    if not settings.RECON_SIMULATOR_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Simulator is disabled. Set RECON_SIMULATOR_ENABLED=true to use it. "
                "The simulator is not part of the real recovery path."
            ),
        )


@router.post("/events", response_model=SimulateEventResponse, status_code=status.HTTP_201_CREATED)
def trigger_simulated_event(
    request: SimulateEventRequest,
    db: Session = Depends(get_db),
):
    """
    Triggers a synthetic payment event through the live RECON OS ingestion pipeline.
    Creates real records in events, payments, customers, recovery_cases, and audit_logs.
    """
    _require_simulator_enabled()
    try:
        merchant = seed_default_merchant(db)
        response = simulate_event(db=db, request=request, merchant_id=merchant.id)
        return response
    except Exception as e:
        logger.error(f"Simulator error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Simulator failed: {str(e)}"
        )


@router.post("/payment-link-paid", response_model=SimulateEventResponse, status_code=status.HTTP_201_CREATED)
def trigger_simulated_payment_link_paid(
    request: SimulatePaymentLinkPaidRequest,
    db: Session = Depends(get_db),
):
    """
    SIMULATED payment confirmation — NOT a real payment. Only usable when
    RECON_SIMULATOR_ENABLED=true. Marks the action outcome via the same validated
    pipeline as a real webhook, but stamps simulated=true everywhere.
    """
    _require_simulator_enabled()
    try:
        merchant = seed_default_merchant(db)
        return simulate_payment_link_paid(db=db, request=request, merchant_id=merchant.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Simulator (payment_link.paid) error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Simulator failed: {str(e)}"
        )
