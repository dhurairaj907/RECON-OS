"""
RECON OS — Phase 3: Outcome Verification  (SAFETY-CRITICAL)

Turns "Razorpay says this payment link was paid" into a validated RECON recovery.
Reached from two authoritative sources ONLY:

  1. a signature-verified `payment_link.paid` webhook   (event_processor step 6a)
  2. an authoritative reconcile pull GET /v1/payment_links/{id}  (actions/reconcile.py)

The gated simulator (when explicitly enabled) also routes here, but every record
and audit entry it produces is stamped `simulated=true`.

`apply_recovery()` is the single validated state transition — used by all three
paths. It enforces, in order:

  * idempotency         (already RECOVERED -> no double count)
  * action-state check  (must be an action WE executed, with a real payment link)
  * currency match
  * FULL amount         (amount_paid >= expected -> RECOVERED ; else -> PARTIAL, case NOT resolved)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.payment import Payment
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase

logger = logging.getLogger("recon.services.actions.verification")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db, action: RecoveryAction, event: str, detail: str, meta: dict):
    base = {"action_id": str(action.id), "reference_id": action.reference_id,
            "payment_link_id": action.provider_action_id}
    base.update(meta)
    db.add(AuditLog(
        merchant_id=action.merchant_id,
        recovery_case_id=action.recovery_case_id,
        actor="RECON_ENGINE",
        action=event,
        detail=detail,
        metadata_json=base,
    ))


def _find_action(db: Session, merchant_id, *, reference_id: str | None,
                 payment_link_id: str | None) -> RecoveryAction | None:
    q = db.query(RecoveryAction).filter(RecoveryAction.merchant_id == merchant_id)
    action = None
    if reference_id:
        action = q.filter(RecoveryAction.reference_id == reference_id).first()
    if action is None and payment_link_id:
        action = q.filter(RecoveryAction.provider_action_id == payment_link_id).first()
    return action


# ---------------------------------------------------------------------------
# The single validated state transition
# ---------------------------------------------------------------------------
def apply_recovery(
    db: Session,
    action: RecoveryAction,
    *,
    amount_paid_paise: int | None,
    currency: str | None,
    source_event_id: str,
    provider_status: str | None = "paid",
    simulated: bool = False,
) -> RecoveryAction:
    """Validate a 'paid' signal and, only if it passes every check, mark RECOVERED."""
    tag = "SIMULATED " if simulated else ""

    # 1. Idempotency — never double-count
    if (action.outcome or "").upper() == "RECOVERED":
        _audit(db, action, "RECOVERY_ALREADY_VERIFIED",
               f"{tag}Duplicate paid signal for {action.reference_id} ignored — revenue not double-counted",
               {"source_event_id": source_event_id, "simulated": simulated})
        return action

    # 2. Action-state check — must be an action RECON actually executed
    if (action.status or "").upper() != "EXECUTED" or not action.provider_action_id:
        _audit(db, action, "RECOVERY_REJECTED",
               f"{tag}Paid signal rejected — action {action.reference_id} is "
               f"{action.status}/{action.outcome} with no executed payment link",
               {"source_event_id": source_event_id, "reason": "ACTION_NOT_EXECUTED",
                "simulated": simulated})
        return action

    expected_paise = int(action.amount_paise or 0)
    paid_paise = int(amount_paid_paise or 0)
    action_currency = (action.currency or "INR").upper()
    ev_currency = (currency or action_currency).upper()

    # 3. Currency match
    if ev_currency != action_currency:
        _audit(db, action, "RECOVERY_REJECTED",
               f"{tag}Paid signal rejected — currency mismatch "
               f"(expected {action_currency}, got {ev_currency})",
               {"source_event_id": source_event_id, "reason": "CURRENCY_MISMATCH",
                "expected_currency": action_currency, "event_currency": ev_currency,
                "simulated": simulated})
        return action

    # 4. FULL amount required
    if paid_paise < expected_paise:
        partial_amt = (Decimal(paid_paise) / Decimal("100")).quantize(Decimal("0.01"))
        action.outcome = "PARTIAL"
        action.provider_status = provider_status or "partially_paid"
        action.recovered_amount = Decimal("0.00")   # PARTIAL is NOT recovered revenue
        action.simulated = bool(simulated)
        _audit(db, action, "RECOVERY_PARTIAL",
               f"{tag}Partial payment on {action.reference_id}: paid {action_currency} {partial_amt} "
               f"of {action_currency} {(Decimal(expected_paise)/100):.2f} — NOT recovered, case NOT resolved",
               {"source_event_id": source_event_id, "amount_paid": str(partial_amt),
                "amount_expected": str(Decimal(expected_paise) / 100), "simulated": simulated})
        logger.info("Recovery PARTIAL for %s (%s of %s paise)", action.reference_id,
                    paid_paise, expected_paise)
        return action

    # 5. RECOVERED
    recovered = (Decimal(paid_paise) / Decimal("100")).quantize(Decimal("0.01"))
    action.outcome = "RECOVERED"
    action.provider_status = "paid"
    action.recovered_amount = recovered
    action.completed_at = _now()
    action.verifying_event_id = source_event_id
    action.simulated = bool(simulated)

    case = db.query(RecoveryCase).filter(RecoveryCase.id == action.recovery_case_id).first()
    if case is not None and (case.status or "").upper() not in ("RESOLVED", "CLOSED"):
        case.status = "RESOLVED"
        case.amount_recovered = recovered
        case.resolved_at = _now()

    _audit(db, action, "RECOVERY_VERIFIED",
           f"{tag}Payment confirmed for {action.reference_id} — recovered "
           f"{action_currency} {recovered}"
           + (" (SIMULATED — not a real payment)" if simulated else ""),
           {"source_event_id": source_event_id, "recovered_amount": str(recovered),
            "provider_status": provider_status, "simulated": simulated})
    if case is not None:
        _audit(db, action, "RECOVERY_CASE_RESOLVED",
               f"{tag}Resolved case {case.case_number} via verified Payment Link recovery of "
               f"{action_currency} {recovered}"
               + (" (SIMULATED)" if simulated else ""),
               {"case_number": case.case_number, "amount_recovered": str(recovered),
                "simulated": simulated})
    logger.info("Recovery %sVERIFIED for %s via %s",
                "(SIMULATED) " if simulated else "",
                case.case_number if case else action.recovery_case_id, source_event_id)

    # Phase 7: controlled automatic thank-you communication (advisory, off by
    # default, never able to affect the verified outcome above — see
    # services/communications/automation.py). Never sent for a simulated
    # recovery, which is not a real customer payment.
    if case is not None and not simulated:
        try:
            from services.communications.automation import on_recovery_verified
            on_recovery_verified(db, merchant_id=action.merchant_id, case=case, action=action)
        except Exception:
            logger.exception("Automatic post-recovery communication hook failed for %s (non-fatal)",
                            action.reference_id)

    return action


def mark_link_terminal(db: Session, action: RecoveryAction, plink_status: str,
                       source_event_id: str) -> RecoveryAction:
    """Record an expired / cancelled payment link (case is NOT resolved)."""
    s = (plink_status or "").lower()
    outcome = "EXPIRED" if s == "expired" else "CANCELLED" if s == "cancelled" else None
    if outcome is None or (action.outcome or "").upper() in ("RECOVERED", "PARTIAL"):
        return action
    action.outcome = outcome
    action.provider_status = s
    _audit(db, action, "RECOVERY_FAILED",
           f"Payment link {action.reference_id} is {s} — recovery not completed",
           {"source_event_id": source_event_id, "plink_status": s})
    return action


# ---------------------------------------------------------------------------
# Webhook path (event_processor step 6a)
# ---------------------------------------------------------------------------
def verify_payment_link_recovery(
    db: Session, normalized: dict, merchant_id, revenue_event_id: str
) -> RecoveryAction | None:
    """
    Handle a `payment_link.*` event that has ALREADY passed signature verification
    and event-idempotency in the pipeline. Returns the matched action or None.
    """
    ref = normalized.get("payment_link_reference_id")
    plink_id = normalized.get("razorpay_payment_link_id")
    if not ref and not plink_id:
        return None

    action = _find_action(db, merchant_id, reference_id=ref, payment_link_id=plink_id)
    if action is None:
        logger.info("payment_link event: no RECON action for ref=%s plink=%s", ref, plink_id)
        return None

    event_id = normalized.get("razorpay_event_id") or revenue_event_id
    simulated = bool(normalized.get("recon_simulated"))
    plink_status = (normalized.get("payment_link_status") or "").lower()

    # Phase 9 — correlate the Payment row event_processor.py step 5 already
    # created/updated from this same event's nested payment entity (the
    # payment that actually fulfilled this payment link). Pure correlation
    # pointer for analytics to later net out a refund/dispute on THIS
    # specific payment from recovered revenue — never read by the Action
    # Engine or Policy Engine, never gates anything here.
    if action.fulfilling_payment_id is None:
        fulfilling_rzp_id = normalized.get("razorpay_payment_id")
        if fulfilling_rzp_id:
            fulfilling_payment = db.query(Payment).filter(
                Payment.razorpay_payment_id == fulfilling_rzp_id,
                Payment.merchant_id == merchant_id,
            ).first()
            if fulfilling_payment is not None:
                action.fulfilling_payment_id = fulfilling_payment.id

    if plink_status in ("expired", "cancelled"):
        return mark_link_terminal(db, action, plink_status, event_id)

    # "paid" (full) or "partially_paid" — apply_recovery enforces the full-amount
    # rule: >= expected -> RECOVERED ; short -> PARTIAL (case NOT resolved).
    if plink_status not in ("paid", "partially_paid"):
        _audit(db, action, "RECOVERY_REJECTED",
               f"payment_link event ignored — payment_link.status='{plink_status or 'unknown'}' "
               f"(not paid / partially_paid)",
               {"source_event_id": event_id, "reason": "STATUS_NOT_PAID",
                "plink_status": plink_status, "simulated": simulated})
        return action

    amount_paid = (
        normalized.get("payment_link_amount_paid")
        or normalized.get("amount_paise")
        or normalized.get("payment_link_amount")
    )
    return apply_recovery(
        db, action,
        amount_paid_paise=amount_paid,
        currency=normalized.get("currency"),
        source_event_id=event_id,
        provider_status=plink_status,
        simulated=simulated,
    )
