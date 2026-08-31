"""
RECON OS — Phase 7: Provider Delivery-Status Webhook

    POST /api/v1/webhooks/communications/delivery

A trusted callback from an email/SMS/WhatsApp provider reporting that a
message RECON already sent was actually delivered (or definitively failed
delivery, e.g. a bounce). This is the ONLY way a Communication row can ever
move from SENT to DELIVERED — nothing in the send path, the frontend, or any
authenticated API request can set DELIVERED directly, since a provider
accepting a request only ever means SENT (see
services/communications/service.py / providers.py).

Security:
  * FAIL-CLOSED HMAC-SHA256 signature verification, exactly like the
    Razorpay webhook (see services/communications/webhook_verifier.py) —
    rejected unless signed, unless COMMUNICATION_ALLOW_UNSIGNED_WEBHOOKS is
    explicitly set (local dev only).
  * Idempotent: `event_id` is compared against the row's
    `last_webhook_event_id` — a replayed/duplicate delivery of the SAME
    event is a safe no-op, never double-processed or double-audited.
  * Organization-safe: the row to update is looked up ONLY by
    `provider_message_id` (a value RECON itself generated/received when it
    sent the message) — the payload never carries and is never trusted for
    an organization/merchant id. The audit entry uses the row's OWN
    merchant_id, so this can never cross an organization boundary.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from models.audit_log import AuditLog
from models.communication import Communication
from services.communications.webhook_verifier import verify_communication_webhook_signature

logger = logging.getLogger("recon.routers.communication_webhooks")
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

_ELIGIBLE_SOURCE_STATUS = {"SENT"}
_TARGET_STATUS = {"delivered": "DELIVERED", "failed": "FAILED"}


@router.post("/communications/delivery", status_code=status.HTTP_200_OK)
async def handle_communication_delivery_webhook(
    request: Request,
    x_recon_comm_signature: str | None = Header(default=None, alias="X-RECON-Comm-Signature"),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    if not raw_body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty webhook body")

    if not verify_communication_webhook_signature(raw_body, x_recon_comm_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing webhook signature")

    import json
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload")

    provider_message_id = payload.get("provider_message_id")
    event_id = payload.get("event_id")
    raw_status = str(payload.get("status") or "").strip().lower()
    error_reason = payload.get("error_reason")

    if not provider_message_id or not event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="provider_message_id and event_id are required")
    target_status = _TARGET_STATUS.get(raw_status)
    if target_status is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unsupported status '{raw_status}' — expected 'delivered' or 'failed'")

    comm = db.query(Communication).filter(Communication.provider_message_id == provider_message_id).first()
    if comm is None:
        # Never reveal whether a given id exists to an unauthenticated caller
        # beyond what the 200 response already implies for a valid signature.
        logger.info("Communication delivery webhook: no row for provider_message_id=%s", provider_message_id)
        return {"status": "ignored", "reason": "unknown_provider_message_id"}

    if comm.last_webhook_event_id == event_id:
        return {"status": "ignored", "reason": "duplicate_event", "communication_id": str(comm.id)}

    if comm.status not in _ELIGIBLE_SOURCE_STATUS:
        # Already DELIVERED/FAILED/CANCELLED/etc — a delivery callback can
        # never move a message backwards or re-fabricate a different terminal
        # state.
        comm.last_webhook_event_id = event_id
        db.commit()
        return {"status": "ignored", "reason": f"communication already {comm.status}",
                "communication_id": str(comm.id)}

    comm.status = target_status
    comm.last_webhook_event_id = event_id
    if target_status == "FAILED" and error_reason:
        comm.error_message = str(error_reason)[:1000]
        comm.error_code = comm.error_code or "DELIVERY_FAILED"

    db.add(AuditLog(
        merchant_id=comm.merchant_id, recovery_case_id=comm.recovery_case_id,
        actor="COMMUNICATION_PROVIDER_WEBHOOK",
        action="COMMUNICATION_DELIVERY_STATUS_UPDATED",
        detail=f"{comm.channel}/{comm.message_type} for communication {comm.id} -> {target_status} "
               f"(provider event {event_id})",
        metadata_json={"provider_message_id": provider_message_id, "event_id": event_id,
                       "status": target_status, "error_reason": error_reason},
    ))
    db.commit()
    db.refresh(comm)
    logger.info("Communication %s delivery status -> %s via webhook event %s", comm.id, target_status, event_id)
    return {"status": "ok", "communication_id": str(comm.id), "new_status": target_status}
