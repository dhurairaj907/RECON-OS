"""
RECON OS — Communications Router  (Phase 5)

    POST /api/v1/recovery-cases/{case_id}/communications/send   send a recovery message
    GET  /api/v1/recovery-cases/{case_id}/communications         communication history

Sending requires OPERATOR or ADMIN — same tier as executing a recovery
action. The endpoint NEVER trusts a client-supplied "approved"/"eligible"
flag: it always re-derives eligibility server-side via
services.communications.service.decide_communication, which reads the
CURRENT Policy Engine verdict and RecoveryAction approval state.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from auth import AuthContext, ROLE_ADMIN, ROLE_OPERATOR, get_auth_context, require_role
from database import get_db, get_org_merchant
from models.communication import Communication
from models.recovery_case import RecoveryCase
from schemas.communication import (
    CommunicationListResponse,
    CommunicationResponse,
    SendCommunicationRequest,
    SendCommunicationResponse,
    SequenceEvaluationResponse,
)
from security import rate_limit, require_api_key
from services.communications.automation import evaluate_reminder_sequence
from services.communications.service import send_communication

router = APIRouter(tags=["Communications"])


def _resolve_case(db: Session, merchant_id, case_id: str) -> RecoveryCase:
    q = db.query(RecoveryCase).options(joinedload(RecoveryCase.customer)).filter(
        RecoveryCase.merchant_id == merchant_id
    )
    try:
        uid = UUID(case_id)
        case = q.filter((RecoveryCase.id == uid) | (RecoveryCase.case_number == case_id)).first()
    except ValueError:
        case = q.filter(RecoveryCase.case_number == case_id).first()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recovery case not found")
    return case


def _to_response(c: Communication) -> CommunicationResponse:
    return CommunicationResponse(
        id=str(c.id),
        recovery_case_id=str(c.recovery_case_id),
        recovery_action_id=str(c.recovery_action_id) if c.recovery_action_id else None,
        channel=c.channel, message_type=c.message_type, status=c.status,
        provider=c.provider, recipient=c.recipient, subject=c.subject, body=c.body,
        provider_message_id=c.provider_message_id, error_code=c.error_code,
        error_message=c.error_message, skipped_reason=c.skipped_reason,
        idempotency_key=c.idempotency_key,
        created_at=c.created_at, sent_at=c.sent_at,
    )


@router.post(
    "/recovery-cases/{case_id}/communications/send",
    response_model=SendCommunicationResponse,
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)
def send_case_communication(
    case_id: str,
    payload: SendCommunicationRequest,
    ctx: AuthContext = Depends(require_role(ROLE_OPERATOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    merchant = get_org_merchant(db, ctx.organization)
    case = _resolve_case(db, merchant.id, case_id)

    result = send_communication(
        db, merchant_id=merchant.id, case=case, channel=payload.channel,
        message_type=payload.message_type, decided_by=ctx.user.email,
    )

    if result.status in ("SENT", "DELIVERED"):
        msg = f"{payload.channel} message sent via {result.provider}."
        ok = True
    elif result.status == "FAILED":
        msg = f"Send failed: {result.error_code} — {result.error_message}"
        ok = False
    elif result.status == "OPTED_OUT":
        msg = "Not sent — customer has opted out of this channel."
        ok = False
    else:
        msg = f"Not sent: {result.error_message or result.skipped_reason}"
        ok = False

    return SendCommunicationResponse(ok=ok, message=msg, communication=_to_response(result))


@router.post(
    "/recovery-cases/{case_id}/communications/evaluate-sequence",
    response_model=SequenceEvaluationResponse,
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)
def evaluate_case_communication_sequence(
    case_id: str,
    ctx: AuthContext = Depends(require_role(ROLE_OPERATOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Evaluates (and, only if every safety condition passes, sends) the next
    step in RECON's minimal safe automatic recovery sequence — a single
    follow-up reminder. A no-op unless AUTOMATIC_COMMUNICATIONS_ENABLED.
    RECON OS has no background scheduler in this phase; an external cron/
    queue worker (or an operator) is expected to call this on a cadence —
    calling it repeatedly is always safe, since every stop condition
    (recovered, closed, opted out, limit reached, too soon) is re-checked
    fresh every time, exactly like a manual send.
    """
    merchant = get_org_merchant(db, ctx.organization)
    case = _resolve_case(db, merchant.id, case_id)
    decision = evaluate_reminder_sequence(db, merchant_id=merchant.id, case=case)
    return SequenceEvaluationResponse(
        ok=decision.sent, message=decision.reason,
        communication=_to_response(decision.communication) if decision.communication else None,
    )


@router.get("/recovery-cases/{case_id}/communications", response_model=CommunicationListResponse)
def list_case_communications(
    case_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    merchant = get_org_merchant(db, ctx.organization)
    case = _resolve_case(db, merchant.id, case_id)
    rows = (
        db.query(Communication)
        .filter(Communication.merchant_id == merchant.id, Communication.recovery_case_id == case.id)
        .order_by(Communication.created_at.desc())
        .all()
    )
    return CommunicationListResponse(items=[_to_response(r) for r in rows], total=len(rows))
