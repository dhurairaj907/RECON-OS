"""
RECON OS — Simulator Router

Endpoints for triggering simulated payment events during development and demos.
Feeds through the exact same database and event processing pipeline.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db, seed_default_merchant
from schemas.simulator import SimulateEventRequest, SimulateEventResponse
from services.simulator_service import simulate_event

logger = logging.getLogger("recon.routers.simulator")
router = APIRouter(prefix="/simulator", tags=["Simulator"])


@router.post("/events", response_model=SimulateEventResponse, status_code=status.HTTP_201_CREATED)
def trigger_simulated_event(
    request: SimulateEventRequest,
    db: Session = Depends(get_db),
):
    """
    Triggers a synthetic payment event through the live RECON OS ingestion pipeline.
    Creates real records in events, payments, customers, recovery_cases, and audit_logs.
    """
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
