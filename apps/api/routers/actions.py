"""
RECON OS — Actions Router  (Phase 3: ACT)

    GET  /api/v1/recovery-cases/{case_id}/actions            action history for a case
    POST /api/v1/recovery-cases/{case_id}/actions/propose    create/return an action proposal
    POST /api/v1/actions/{action_id}/execute                 execute (server re-checks policy)
    GET  /api/v1/actions/{action_id}                         action status / result
    GET  /api/v1/actions                                     all actions (history)

The frontend NEVER supplies a policy verdict, an approval, provider ids, or
Razorpay credentials. The backend owns all of those.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from database import get_db, seed_default_merchant
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from schemas.action import (
    ActionListResponse,
    ActionResponse,
    ExecuteActionResponse,
)
from services.actions.common import ui_state
from services.actions.executor import execute_action
from services.actions.proposal import build_proposal, get_or_create_action

logger = logging.getLogger("recon.routers.actions")

router = APIRouter(tags=["Actions"])


# ---------------------------------------------------------------------------
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


def _case_number(db: Session, case_id) -> str | None:
    c = db.query(RecoveryCase.case_number).filter(RecoveryCase.id == case_id).first()
    return c[0] if c else None


def _to_response(db: Session, action: RecoveryAction) -> ActionResponse:
    return ActionResponse(
        id=str(action.id),
        recovery_case_id=str(action.recovery_case_id),
        case_number=_case_number(db, action.recovery_case_id),
        action_type=action.action_type,
        status=action.status,
        outcome=action.outcome,
        ui_state=ui_state(action),
        reference_id=action.reference_id,
        provider=action.provider,
        provider_action_id=action.provider_action_id,
        provider_status=action.provider_status,
        payment_link_url=action.payment_link_url,
        amount=action.amount,
        currency=action.currency,
        recovered_amount=action.recovered_amount or 0,
        strategy_action=action.strategy_action,
        policy_verdict=action.policy_verdict,
        blocked_reason=action.blocked_reason,
        error_code=action.error_code,
        error_message=action.error_message,
        requested_at=action.requested_at,
        approved_at=action.approved_at,
        executed_at=action.executed_at,
        completed_at=action.completed_at,
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


# ---------------------------------------------------------------------------
@router.get("/recovery-cases/{case_id}/actions", response_model=ActionListResponse)
def list_case_actions(case_id: str, db: Session = Depends(get_db)):
    merchant = seed_default_merchant(db)
    case = _resolve_case(db, merchant.id, case_id)
    rows = (
        db.query(RecoveryAction)
        .filter(RecoveryAction.recovery_case_id == case.id)
        .order_by(desc(RecoveryAction.created_at))
        .all()
    )
    return ActionListResponse(items=[_to_response(db, r) for r in rows], total=len(rows))


@router.post("/recovery-cases/{case_id}/actions/propose")
def propose_case_action(case_id: str, db: Session = Depends(get_db)):
    """
    Build (and, if executable, persist) an action proposal from the latest
    deterministic strategy/policy result. Idempotent: at most one
    CREATE_PAYMENT_LINK action per recovery case.
    """
    merchant = seed_default_merchant(db)
    case = _resolve_case(db, merchant.id, case_id)
    action, proposal = get_or_create_action(db, case)
    return {
        "proposal": proposal.model_dump(mode="json"),
        "action": _to_response(db, action).model_dump(mode="json") if action else None,
    }


@router.post("/actions/{action_id}/execute", response_model=ExecuteActionResponse)
def execute_recovery_action(action_id: str, db: Session = Depends(get_db)):
    """
    Execute a proposed action. The Policy Engine is RE-EVALUATED server-side
    here — a stored / frontend / AI 'approved' value is never trusted.
    Safe to repeat: a created Payment Link is never created twice.
    """
    merchant = seed_default_merchant(db)
    try:
        uid = UUID(action_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action id")

    action = db.query(RecoveryAction).filter(
        RecoveryAction.id == uid, RecoveryAction.merchant_id == merchant.id
    ).first()
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    result = execute_action(db, action.id)
    resp = _to_response(db, result)

    if result.status == "EXECUTED":
        msg = "Payment Link created. Awaiting customer payment — revenue is not yet recovered."
    elif result.status == "BLOCKED":
        msg = f"Execution blocked: {result.blocked_reason} — {result.error_message}"
    elif result.status == "FAILED":
        msg = f"Execution failed: {result.error_code} — {result.error_message}"
    else:
        msg = f"Action is {result.status}."

    return ExecuteActionResponse(ok=result.status == "EXECUTED", message=msg, action=resp)


@router.get("/actions/{action_id}", response_model=ActionResponse)
def get_action(action_id: str, db: Session = Depends(get_db)):
    merchant = seed_default_merchant(db)
    try:
        uid = UUID(action_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action id")
    action = db.query(RecoveryAction).filter(
        RecoveryAction.id == uid, RecoveryAction.merchant_id == merchant.id
    ).first()
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return _to_response(db, action)


@router.get("/actions", response_model=ActionListResponse)
def list_actions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    outcome: str | None = Query(None),
    db: Session = Depends(get_db),
):
    merchant = seed_default_merchant(db)
    q = db.query(RecoveryAction).filter(RecoveryAction.merchant_id == merchant.id)
    if status_filter:
        q = q.filter(RecoveryAction.status == status_filter)
    if outcome:
        q = q.filter(RecoveryAction.outcome == outcome)
    total = q.count()
    rows = q.order_by(desc(RecoveryAction.created_at)).offset((page - 1) * limit).limit(limit).all()
    return ActionListResponse(items=[_to_response(db, r) for r in rows], total=total)
