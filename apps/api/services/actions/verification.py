"""
RECON OS — Phase 3: Outcome Verification

Called from the Phase 1 event processor when a `payment_link.paid` webhook
arrives. Correlates the event to a RECON action via `reference_id` (preferred)
or the Razorpay payment link id, then:

  * marks the action outcome RECOVERED
  * records the actually-paid amount
  * resolves the recovery case and sets `amount_recovered`
  * writes the audit trail

Double-count safe:
  * upstream: the RevenueEvent unique constraint blocks re-processing the same event
  * here: if the action is already RECOVERED, revenue is NOT touched again

Creating a Payment Link never marks revenue recovered — only this path does.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase

logger = logging.getLogger("recon.services.actions.verification")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _amount_recovered(normalized: dict, action: RecoveryAction) -> Decimal:
    paise = (
        normalized.get("payment_link_amount_paid")
        or normalized.get("amount_paise")
        or normalized.get("payment_link_amount")
        or action.amount_paise
    )
    if paise:
        try:
            return (Decimal(str(paise)) / Decimal("100")).quantize(Decimal("0.01"))
        except Exception:
            pass
    return Decimal(action.amount or 0)


def verify_payment_link_recovery(
    db: Session, normalized: dict, merchant_id, revenue_event_id: str
) -> RecoveryAction | None:
    """Returns the matched action (updated) or None if no RECON action matches."""
    ref = normalized.get("payment_link_reference_id")
    plink_id = normalized.get("razorpay_payment_link_id")
    if not ref and not plink_id:
        return None

    q = db.query(RecoveryAction).filter(RecoveryAction.merchant_id == merchant_id)
    action = None
    if ref:
        action = q.filter(RecoveryAction.reference_id == ref).first()
    if action is None and plink_id:
        action = q.filter(RecoveryAction.provider_action_id == plink_id).first()
    if action is None:
        logger.info("payment_link.paid: no RECON action for ref=%s plink=%s", ref, plink_id)
        return None

    event_id = normalized.get("razorpay_event_id") or revenue_event_id

    # --- DOUBLE-COUNT GUARD -------------------------------------------------
    if (action.outcome or "").upper() == "RECOVERED":
        db.add(AuditLog(
            merchant_id=merchant_id,
            recovery_case_id=action.recovery_case_id,
            actor="RECON_ENGINE",
            action="RECOVERY_ALREADY_VERIFIED",
            detail=f"Duplicate payment_link.paid for {action.reference_id} ignored "
                   f"(revenue not double-counted)",
            metadata_json={"action_id": str(action.id), "event_id": event_id,
                           "reference_id": action.reference_id},
        ))
        return action

    recovered = _amount_recovered(normalized, action)

    action.outcome = "RECOVERED"
    action.provider_status = normalized.get("payment_link_status") or "paid"
    action.recovered_amount = recovered
    action.completed_at = _now()
    action.verifying_event_id = event_id

    case = db.query(RecoveryCase).filter(RecoveryCase.id == action.recovery_case_id).first()
    if case is not None and (case.status or "").upper() not in ("RESOLVED", "CLOSED"):
        case.status = "RESOLVED"
        case.amount_recovered = recovered
        case.resolved_at = _now()

    db.add(AuditLog(
        merchant_id=merchant_id,
        recovery_case_id=action.recovery_case_id,
        actor="RECON_ENGINE",
        action="RECOVERY_VERIFIED",
        detail=(f"Payment confirmed via payment_link.paid — {action.reference_id} "
                f"recovered {case.currency if case else 'INR'} {recovered}"),
        metadata_json={
            "action_id": str(action.id),
            "reference_id": action.reference_id,
            "payment_link_id": action.provider_action_id,
            "recovered_amount": str(recovered),
            "event_id": event_id,
        },
    ))
    if case is not None:
        db.add(AuditLog(
            merchant_id=merchant_id,
            recovery_case_id=case.id,
            actor="RECON_ENGINE",
            action="RECOVERY_CASE_RESOLVED",
            detail=f"Resolved case {case.case_number} via verified Payment Link recovery of "
                   f"{case.currency} {recovered}",
            metadata_json={"case_number": case.case_number,
                           "reference_id": action.reference_id,
                           "amount_recovered": str(recovered)},
        ))
    logger.info("Recovery VERIFIED for %s via %s (%s)",
                case.case_number if case else action.recovery_case_id,
                action.reference_id, event_id)
    return action
