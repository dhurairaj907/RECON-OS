"""
RECON OS — Actions Router  (Phase 3: ACT)

    GET  /api/v1/recovery-cases/{case_id}/actions            action history for a case
    POST /api/v1/recovery-cases/{case_id}/actions/propose    create/return an action proposal
    POST /api/v1/actions/{action_id}/execute                 execute (server re-checks policy)
    POST /api/v1/actions/{action_id}/approve                 human approval (Phase 4) — re-validates, then executes
    POST /api/v1/actions/{action_id}/reject                  human rejection (Phase 4) — terminal, never executes
    POST /api/v1/actions/{action_id}/verify-unknown           resolve an UNKNOWN outcome (Phase 4) — never a blind retry
    GET  /api/v1/actions/{action_id}                         action status / result
    GET  /api/v1/actions                                     all actions (history)

The frontend NEVER supplies a policy verdict, an approval, provider ids, or
Razorpay credentials. The backend owns all of those. A human's approve/reject
click only records a DECISION — it never bypasses the Policy Engine, which is
always re-evaluated against current state before anything executes.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from auth import AuthContext, ROLE_ADMIN, ROLE_APPROVER, ROLE_OPERATOR, get_auth_context, require_role
from config import settings
from database import get_db, get_org_merchant
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from schemas.action import (
    ActionListResponse,
    ActionResponse,
    ExecuteActionResponse,
    ReconcileActionResponse,
)
from security import rate_limit, require_api_key
from services.actions.approval import approve_action, reject_action
from services.actions.common import ui_state
from services.actions.executor import execute_action
from services.actions.proposal import build_proposal, get_or_create_action
from services.actions.reconcile import reconcile_action
from services.actions.unknown import verify_unknown_action

# Applied to every endpoint that proposes, executes, approves, rejects,
# verifies, or reconciles a recovery action — never to read-only GETs. See
# security.py: an API key check (open by default for local dev) plus a
# per-IP rate limit, sitting in front of the Policy Engine / idempotency
# guards those endpoints already enforce, not replacing them.
_PROTECTED = [Depends(require_api_key), Depends(rate_limit)]

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


def _load_action(db: Session, merchant_id, action_id: str) -> RecoveryAction:
    try:
        uid = UUID(action_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action id")
    action = db.query(RecoveryAction).filter(
        RecoveryAction.id == uid, RecoveryAction.merchant_id == merchant_id
    ).first()
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return action


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
        simulated=bool(action.simulated),
        simulator_enabled=bool(settings.RECON_SIMULATOR_ENABLED),
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
        human_decision=action.human_decision,
        human_decided_at=action.human_decided_at,
        human_decided_by=action.human_decided_by,
    )


# ---------------------------------------------------------------------------
@router.get("/recovery-cases/{case_id}/actions", response_model=ActionListResponse)
def list_case_actions(case_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    merchant = get_org_merchant(db, ctx.organization)
    case = _resolve_case(db, merchant.id, case_id)
    rows = (
        db.query(RecoveryAction)
        .filter(RecoveryAction.recovery_case_id == case.id)
        .order_by(desc(RecoveryAction.created_at))
        .all()
    )
    return ActionListResponse(items=[_to_response(db, r) for r in rows], total=len(rows))


@router.post("/recovery-cases/{case_id}/actions/propose", dependencies=_PROTECTED)
def propose_case_action(
    case_id: str,
    ctx: AuthContext = Depends(require_role(ROLE_OPERATOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Build (and, if executable, persist) an action proposal from the latest
    deterministic strategy/policy result. Idempotent: at most one
    CREATE_PAYMENT_LINK action per recovery case.
    """
    merchant = get_org_merchant(db, ctx.organization)
    case = _resolve_case(db, merchant.id, case_id)
    action, proposal = get_or_create_action(db, case)
    return {
        "proposal": proposal.model_dump(mode="json"),
        "action": _to_response(db, action).model_dump(mode="json") if action else None,
    }


@router.post("/actions/{action_id}/execute", response_model=ExecuteActionResponse, dependencies=_PROTECTED)
def execute_recovery_action(
    action_id: str,
    ctx: AuthContext = Depends(require_role(ROLE_OPERATOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Execute a proposed action. The Policy Engine is RE-EVALUATED server-side
    here — a stored / frontend / AI 'approved' value is never trusted.
    Safe to repeat: a created Payment Link is never created twice.
    """
    merchant = get_org_merchant(db, ctx.organization)
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


@router.post("/actions/{action_id}/approve", response_model=ExecuteActionResponse, dependencies=_PROTECTED)
def approve_recovery_action(
    action_id: str,
    ctx: AuthContext = Depends(require_role(ROLE_APPROVER, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Record a human APPROVE decision for a NEEDS_APPROVAL action, then execute
    through the real Action Engine. Approval never bypasses safety checks: the
    engine independently re-derives case state and re-evaluates policy, and
    only proceeds if that fresh check still permits it (still NEEDS_APPROVAL,
    honouring this decision, or now APPROVED outright — never if now
    REJECTED). Never trusts a stored/frontend "approved" value.
    """
    merchant = get_org_merchant(db, ctx.organization)
    action = _load_action(db, merchant.id, action_id)

    result = approve_action(db, action.id, decided_by=ctx.user.email)
    resp = _to_response(db, result)

    if result.status == "EXECUTED":
        msg = "Approved and executed — Payment Link created. Awaiting customer payment."
    elif result.status == "BLOCKED" and result.blocked_reason == "NEEDS_APPROVAL":
        msg = "Approval recorded, but re-validation still requires approval."
    elif result.status == "BLOCKED":
        msg = f"Approved, but execution is no longer valid: {result.blocked_reason} — {result.error_message}"
    elif result.status == "FAILED":
        msg = f"Approved, but execution failed: {result.error_code} — {result.error_message}"
    elif (result.outcome or "").upper() == "UNKNOWN":
        msg = "Approved and execution attempted, but the outcome is UNKNOWN — verification required."
    else:
        msg = f"Action is {result.status}."

    return ExecuteActionResponse(ok=result.status == "EXECUTED", message=msg, action=resp)


@router.post("/actions/{action_id}/reject", response_model=ExecuteActionResponse, dependencies=_PROTECTED)
def reject_recovery_action(
    action_id: str,
    ctx: AuthContext = Depends(require_role(ROLE_APPROVER, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Record a human REJECT decision. Terminal — this action will never be
    executed. The recovery case itself is untouched; a new action can still
    be proposed later if circumstances change.
    """
    merchant = get_org_merchant(db, ctx.organization)
    action = _load_action(db, merchant.id, action_id)

    result = reject_action(db, action.id, decided_by=ctx.user.email)
    resp = _to_response(db, result)
    return ExecuteActionResponse(
        ok=False,
        message="Rejected — this action will not be executed.",
        action=resp,
    )


@router.post("/actions/{action_id}/verify-unknown", response_model=ExecuteActionResponse, dependencies=_PROTECTED)
def verify_unknown_recovery_action(
    action_id: str,
    ctx: AuthContext = Depends(require_role(ROLE_OPERATOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Resolve an UNKNOWN outcome by asking Razorpay directly whether the
    Payment Link was actually created — NEVER a blind retry. Safe to repeat;
    idempotent (a no-op once the action is no longer UNKNOWN).
    """
    merchant = get_org_merchant(db, ctx.organization)
    action = _load_action(db, merchant.id, action_id)

    result = verify_unknown_action(db, action.id)
    resp = _to_response(db, result)

    if (result.outcome or "").upper() == "UNKNOWN":
        msg = "Still unable to verify with Razorpay — outcome remains unknown. No retry allowed yet."
        ok = False
    elif result.status == "EXECUTED":
        msg = "Verified — the Payment Link was actually created despite the timeout. No duplicate was made."
        ok = True
    elif result.status == "FAILED":
        msg = "Verified — the original request never reached Razorpay. A new attempt is now policy-gated and safe."
        ok = False
    else:
        msg = f"Action is {result.status}/{result.outcome}."
        ok = False

    return ExecuteActionResponse(ok=ok, message=msg, action=resp)


@router.post("/actions/{action_id}/reconcile", response_model=ReconcileActionResponse, dependencies=_PROTECTED)
def reconcile_recovery_action(
    action_id: str,
    ctx: AuthContext = Depends(require_role(ROLE_OPERATOR, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Ask Razorpay directly whether this action's payment link was actually paid
    (GET /v1/payment_links/{id}) and, ONLY if Razorpay reports status == "paid"
    with the full amount, mark the action RECOVERED. Never fakes a result.
    Safe to repeat; idempotent.
    """
    merchant = get_org_merchant(db, ctx.organization)
    try:
        uid = UUID(action_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action id")

    action = db.query(RecoveryAction).filter(
        RecoveryAction.id == uid, RecoveryAction.merchant_id == merchant.id
    ).first()
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    res = reconcile_action(db, action.id)
    return ReconcileActionResponse(
        ok=res.ok,
        recovered=res.recovered,
        partial=res.partial,
        razorpay_status=res.razorpay_status,
        amount_paid=res.amount_paid,
        message=res.message,
        action=_to_response(db, res.action),
    )


@router.get("/actions/{action_id}", response_model=ActionResponse)
def get_action(action_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    merchant = get_org_merchant(db, ctx.organization)
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
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    merchant = get_org_merchant(db, ctx.organization)
    q = db.query(RecoveryAction).filter(RecoveryAction.merchant_id == merchant.id)
    if status_filter:
        q = q.filter(RecoveryAction.status == status_filter)
    if outcome:
        q = q.filter(RecoveryAction.outcome == outcome)
    total = q.count()
    rows = q.order_by(desc(RecoveryAction.created_at)).offset((page - 1) * limit).limit(limit).all()
    return ActionListResponse(items=[_to_response(db, r) for r in rows], total=total)
