"""
RECON OS — Phase 4: Human Approval Workflow  (SAFETY-CRITICAL)

A NEEDS_APPROVAL verdict means "a human must decide" — never "silently
proceed" and never "flip a stored value and trust it." Approving/rejecting
here does NOT itself authorise execution: it only records a human decision on
the action. The actual re-validation and execution happen through the SAME
`execute_action()` used for every other action, which independently
re-derives case context, diagnosis, prediction, strategy and policy from
CURRENT state every time — exactly as it does for an automatic APPROVED
verdict.

A REJECTED policy verdict is never overridable by a human decision, at any
point — see the REJECTED branch in `executor.py`, which is checked before a
human decision is ever consulted, and which clears any stale approval it
finds.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.recovery_action import RecoveryAction
from services.actions.common import audit_action
from services.actions.executor import execute_action

logger = logging.getLogger("recon.services.actions.approval")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def approve_action(db: Session, action_id, decided_by: str = "OPERATOR") -> RecoveryAction:
    """
    Record a human APPROVE decision, then run the real Action Engine. The
    engine re-evaluates policy against CURRENT state and only proceeds if it
    still says NEEDS_APPROVAL (honouring this decision) or now APPROVED
    outright — never if it is now REJECTED. A stale or now-invalid approval
    (attempts exhausted since, case resolved since, etc.) is not executed.
    """
    action = db.query(RecoveryAction).filter(RecoveryAction.id == action_id).first()
    if action is None:
        raise ValueError(f"Recovery action {action_id} not found")

    # Idempotent no-op — this action already moved past any decision point.
    if action.provider_action_id or action.status in ("EXECUTED", "EXECUTING"):
        logger.info("Approve on %s ignored — already %s", action.reference_id, action.status)
        return action

    if action.human_decision != "APPROVED":
        action.human_decision = "APPROVED"
        action.human_decided_at = _now()
        action.human_decided_by = decided_by
        audit_action(db, action, "HUMAN_OPERATOR", "ACTION_APPROVAL_GRANTED",
                     f"{decided_by} approved execution of {action.reference_id}. "
                     f"Re-validating policy and current state before executing — "
                     f"approval alone does not bypass safety checks.")
        db.commit()
        db.refresh(action)

    return execute_action(db, action.id)


def reject_action(db: Session, action_id, decided_by: str = "OPERATOR",
                  reason: str | None = None) -> RecoveryAction:
    """
    Record a human REJECT decision. Terminal for this action — it will never
    execute. Does not touch the recovery case; a new action can still be
    proposed later through the normal propose flow if circumstances change.
    """
    action = db.query(RecoveryAction).filter(RecoveryAction.id == action_id).first()
    if action is None:
        raise ValueError(f"Recovery action {action_id} not found")

    if action.provider_action_id or action.status in ("EXECUTED", "EXECUTING"):
        logger.info("Reject on %s ignored — already %s", action.reference_id, action.status)
        return action

    action.human_decision = "REJECTED"
    action.human_decided_at = _now()
    action.human_decided_by = decided_by
    action.status = "BLOCKED"
    action.blocked_reason = "HUMAN_REJECTED"
    action.error_code = None
    action.error_message = reason or "Rejected by operator."
    audit_action(db, action, "HUMAN_OPERATOR", "ACTION_REJECTED_BY_HUMAN",
                 f"{decided_by} rejected execution of {action.reference_id}"
                 + (f": {reason}" if reason else "") + ". This action will not be executed.",
                 {"reason": reason})
    db.commit()
    db.refresh(action)
    logger.info("Action %s REJECTED by %s", action.reference_id, decided_by)
    return action
