"""
RECON OS — Webhooks Router

Endpoint for Razorpay inbound webhook events.
Implements:
1. Raw body signature verification
2. Fast response time (no blocking LLM calls)
3. Safe duplicate handling
"""

import json
import logging
from fastapi import APIRouter, Request, HTTPException, Header, Depends, status
from sqlalchemy.orm import Session

from database import get_db, resolve_connected_merchant
from integrations.razorpay.webhook_verifier import verify_webhook_signature
from services.event_processor import process_inbound_event

logger = logging.getLogger("recon.routers.webhooks")
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/razorpay", status_code=status.HTTP_200_OK)
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db),
):
    """
    Receives and processes inbound Razorpay webhook events.
    Verifies HMAC-SHA256 signature using the raw HTTP request body.
    """
    # 1. Read raw body bytes
    raw_body = await request.body()
    if not raw_body:
        logger.warning("Received empty webhook body")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty webhook request body"
        )

    # 2. Verify signature
    if not verify_webhook_signature(raw_body, x_razorpay_signature):
        logger.warning("Invalid webhook signature received")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature"
        )

    # 3. Parse JSON
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Malformed JSON in webhook body: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON payload"
        )

    # 4. Resolve the connected merchant. RECON OS has a single, platform-wide
    # Razorpay credential (see config.py) — every real webhook is attributed
    # to the one canonical default Organization's Merchant, resolved the
    # same deterministic way every other org-scoped router resolves theirs.
    # True multi-tenant routing needs per-organization credentials, which
    # does not exist today (see database.resolve_connected_merchant).
    merchant = resolve_connected_merchant(db)

    # 5. Process through the data pipeline
    try:
        event, case = process_inbound_event(
            db=db,
            raw_payload=payload,
            merchant_id=merchant.id,
            source="razorpay",
            signature_verified=True,
        )
        return {
            "status": "success",
            "event_id": event.razorpay_event_id,
            "event_type": event.event_type,
            "processing_status": event.processing_status,
            "case_number": case.case_number if case else None,
        }
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        # Return 200 to prevent Razorpay storming retries if it's an unrecoverable payload error
        return {
            "status": "error",
            "message": "Event recorded but processing encountered an error"
        }
