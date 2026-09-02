"""
RECON OS — Phase 9: Payment Lifecycle Reconciliation  (SAFETY-CRITICAL)

The single validated Payment lifecycle state transition. Reached ONLY from
services/event_processor.py, after a normalized, idempotency-checked
provider event (the same RevenueEvent uniqueness guard that already
deduplicates every inbound event). Never called by AI, the Action Engine, or
the Policy Engine.

Recovery lifecycle (RecoveryCase.status, RecoveryAction.outcome) is a
SEPARATE concept, owned exclusively by services/actions/verification.py
(Phase 3) and event_processor.py's own capture-resolves-case branch
(Phase 1) — this module never writes either of those. It only observes and
records the PAYMENT's own financial state.

reconcile_payment_lifecycle() is intentionally conservative: whenever a
transition, amount, or identifier check fails, it writes a
RECONCILIATION_MISMATCH audit row and returns WITHOUT mutating the payment's
lifecycle_status or money fields. RECON never silently "fixes" a mismatch —
a human reviews it via GET /api/v1/reconciliation/mismatches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.payment import Payment

logger = logging.getLogger("recon.services.reconciliation")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Deterministic event_type -> lifecycle status for plain payment events.
# Verified against Razorpay's documented webhook events
# (razorpay.com/docs/webhooks/payments/). Refund and dispute events are
# handled separately below (they need the nested refund amount / dispute
# sub-type, not just a flat target status).
TRANSITION_MAP: dict[str, str] = {
    "payment.authorized": "AUTHORIZED",
    "payment.captured": "CAPTURED",
    "order.paid": "CAPTURED",
    "payment.failed": "FAILED",
}

DISPUTE_STATUS_MAP = {
    "payment.dispute.created": "OPEN",
    "payment.dispute.won": "WON",
    "payment.dispute.lost": "LOST",
    "payment.dispute.closed": "WON",  # Razorpay closes a dispute resolved in the merchant's favor as "closed"
}

# Explicit adjacency list. `None` = no prior observation (first event for
# this payment) — SETTLED/EXPIRED/MISMATCHED are terminal (no outgoing
# edges); REFUNDED is terminal (a fully refunded payment cannot un-refund).
ALLOWED_TRANSITIONS: dict[Optional[str], set] = {
    None: {"PENDING", "AUTHORIZED", "CAPTURED", "FAILED"},
    "PENDING": {"AUTHORIZED", "CAPTURED", "FAILED"},
    "AUTHORIZED": {"CAPTURED", "FAILED"},
    "CAPTURED": {"SETTLED", "REFUNDED", "PARTIALLY_REFUNDED", "DISPUTED"},
    "PARTIALLY_REFUNDED": {"REFUNDED", "DISPUTED", "SETTLED"},
    "SETTLED": {"REFUNDED", "PARTIALLY_REFUNDED", "DISPUTED"},
    "DISPUTED": {"REFUNDED", "PARTIALLY_REFUNDED", "SETTLED"},
    "FAILED": set(),
    "REFUNDED": set(),
    "EXPIRED": set(),
    "MISMATCHED": set(),
}

_AUDIT_ACTION_FOR_STATUS = {
    "AUTHORIZED": "PAYMENT_AUTHORIZED",
    "CAPTURED": "PAYMENT_CAPTURED",
    "FAILED": "PAYMENT_FAILED",
    "REFUNDED": "PAYMENT_REFUNDED",
    "PARTIALLY_REFUNDED": "PAYMENT_PARTIALLY_REFUNDED",
}


@dataclass
class ReconciliationOutcome:
    ok: bool                       # True if a real (non-mismatch, non-duplicate-noop) transition applied
    mismatch: bool
    lifecycle_status: Optional[str]
    reconciliation_status: str
    reason: str


def _audit(db: Session, payment: Payment, action: str, detail: str, meta: dict,
           recovery_case_id=None) -> None:
    db.add(AuditLog(
        merchant_id=payment.merchant_id,
        recovery_case_id=recovery_case_id,
        actor="RECON_ENGINE",
        action=action,
        detail=detail,
        metadata_json=meta,
    ))


def _mismatch(db: Session, payment: Payment, *, expected, observed, provider: str,
              identifier: str, reason: str, event_id: str, recovery_case_id=None,
              extra: Optional[dict] = None) -> ReconciliationOutcome:
    meta = {
        "expected_state": str(expected),
        "observed_state": str(observed),
        "provider": provider,
        "identifier": identifier,
        "timestamp": _now().isoformat(),
        "reason": reason,
        "source_event_id": event_id,
    }
    if extra:
        meta.update(extra)
    payment.reconciliation_status = "MISMATCH"
    _audit(db, payment, "RECONCILIATION_MISMATCH",
           f"Reconciliation mismatch for payment {payment.razorpay_payment_id}: {reason} "
           f"(expected={expected}, observed={observed})",
           meta, recovery_case_id=recovery_case_id)
    logger.warning("RECONCILIATION_MISMATCH for %s: %s", payment.razorpay_payment_id, reason)
    return ReconciliationOutcome(ok=False, mismatch=True, lifecycle_status=payment.lifecycle_status,
                                  reconciliation_status="MISMATCH", reason=reason)


def _refund_transition(db: Session, payment: Payment, normalized: dict, *,
                        event_id: str, recovery_case_id=None) -> ReconciliationOutcome:
    identifier = payment.razorpay_payment_id
    prior_status = payment.lifecycle_status
    refund_amount = int(normalized.get("refund_amount_paise") or 0)
    remaining = int(payment.amount_paise or 0) - int(payment.refunded_amount_paise or 0)

    if prior_status is None or "REFUNDED" not in ALLOWED_TRANSITIONS.get(prior_status, set()):
        reason = "UNKNOWN_PAYMENT_IDENTIFIER" if prior_status is None else "INVALID_TRANSITION"
        return _mismatch(db, payment, expected=prior_status, observed="REFUND_RECEIVED",
                          provider="razorpay", identifier=identifier, reason=reason,
                          event_id=event_id, recovery_case_id=recovery_case_id)
    if refund_amount <= 0:
        return _mismatch(db, payment, expected=f"1..{remaining}", observed=refund_amount,
                          provider="razorpay", identifier=identifier, reason="INVALID_REFUND_AMOUNT",
                          event_id=event_id, recovery_case_id=recovery_case_id)
    if refund_amount > remaining:
        return _mismatch(db, payment, expected=f"<= {remaining}", observed=refund_amount,
                          provider="razorpay", identifier=identifier,
                          reason="REFUND_EXCEEDS_CAPTURED_AMOUNT", event_id=event_id,
                          recovery_case_id=recovery_case_id,
                          extra={"remaining_captured_paise": remaining})

    new_refunded = int(payment.refunded_amount_paise or 0) + refund_amount
    target = "REFUNDED" if new_refunded >= int(payment.amount_paise or 0) else "PARTIALLY_REFUNDED"
    payment.refunded_amount_paise = new_refunded
    payment.lifecycle_status = target
    payment.reconciliation_status = "IN_SYNC"
    currency = payment.currency or "INR"
    _audit(db, payment, _AUDIT_ACTION_FOR_STATUS[target],
           f"{'Full' if target == 'REFUNDED' else 'Partial'} refund of {currency} "
           f"{Decimal(refund_amount) / 100:.2f} recorded for payment "
           f"{payment.razorpay_payment_id} (total refunded {currency} "
           f"{Decimal(new_refunded) / 100:.2f} of {currency} "
           f"{Decimal(payment.amount_paise or 0) / 100:.2f}).",
           {"source_event_id": event_id, "refund_amount_paise": refund_amount,
            "total_refunded_paise": new_refunded},
           recovery_case_id=recovery_case_id)
    return ReconciliationOutcome(ok=True, mismatch=False, lifecycle_status=target,
                                  reconciliation_status="IN_SYNC", reason="OK")


def _dispute_transition(db: Session, payment: Payment, normalized: dict, *,
                         event_id: str, recovery_case_id=None) -> ReconciliationOutcome:
    identifier = payment.razorpay_payment_id
    prior_status = payment.lifecycle_status
    event_type = str(normalized.get("event_type") or "")

    if prior_status is None:
        return _mismatch(db, payment, expected=None, observed="DISPUTE_RECEIVED",
                          provider="razorpay", identifier=identifier,
                          reason="UNKNOWN_PAYMENT_IDENTIFIER", event_id=event_id,
                          recovery_case_id=recovery_case_id)
    if prior_status in ("FAILED", "EXPIRED"):
        return _mismatch(db, payment, expected=prior_status, observed="DISPUTE_RECEIVED",
                          provider="razorpay", identifier=identifier,
                          reason="DISPUTE_ON_TERMINAL_NON_CAPTURED_PAYMENT", event_id=event_id,
                          recovery_case_id=recovery_case_id)

    new_dispute_status = DISPUTE_STATUS_MAP.get(event_type, payment.dispute_status)
    payment.dispute_status = new_dispute_status
    # A dispute is recorded as an OVERLAY (dispute_status), never by
    # permanently overwriting the payment's own captured/refunded
    # lifecycle_status — "original recovery + later dispute" both stay
    # visible in the audit timeline rather than one erasing the other.
    # lifecycle_status moves to DISPUTED while the dispute is OPEN; once
    # resolved (WON/LOST) it's recomputed from the payment's own refund
    # amount (never fabricated, never left stuck at DISPUTED forever).
    if new_dispute_status == "OPEN":
        payment.lifecycle_status = "DISPUTED"
    elif int(payment.refunded_amount_paise or 0) >= int(payment.amount_paise or 0) and payment.amount_paise:
        payment.lifecycle_status = "REFUNDED"
    elif int(payment.refunded_amount_paise or 0) > 0:
        payment.lifecycle_status = "PARTIALLY_REFUNDED"
    else:
        payment.lifecycle_status = "CAPTURED"
    payment.reconciliation_status = "IN_SYNC"
    _audit(db, payment, "PAYMENT_DISPUTED",
           f"Dispute status {new_dispute_status} for payment {payment.razorpay_payment_id} "
           f"(prior lifecycle state {prior_status} preserved — a dispute never erases recovery "
           f"history).",
           {"source_event_id": event_id, "dispute_status": new_dispute_status,
            "prior_lifecycle_status": prior_status},
           recovery_case_id=recovery_case_id)
    return ReconciliationOutcome(ok=True, mismatch=False, lifecycle_status=payment.lifecycle_status,
                                  reconciliation_status="IN_SYNC", reason="OK")


def reconcile_payment_lifecycle(
    db: Session,
    payment: Payment,
    normalized: dict,
    *,
    merchant_id,
    event_id: str,
    recovery_case_id=None,
) -> ReconciliationOutcome:
    """
    The one entry point. `payment` must already be the row resolved/upserted
    by event_processor.py step 5 for this event's razorpay_payment_id.
    """
    event_type = str(normalized.get("event_type") or "")
    identifier = payment.razorpay_payment_id

    # Organization mismatch — the payment we resolved belongs to a DIFFERENT
    # merchant than the event claims. Never happens through the single-
    # platform-credential webhook path today, but this is the explicit guard
    # the directive requires — never silently reattribute financial state.
    if payment.merchant_id != merchant_id:
        return _mismatch(db, payment, expected=str(payment.merchant_id), observed=str(merchant_id),
                          provider="razorpay", identifier=identifier,
                          reason="ORGANIZATION_MISMATCH", event_id=event_id,
                          recovery_case_id=recovery_case_id)

    if event_type.startswith("refund."):
        if event_type != "refund.processed":
            # refund.created is an intermediate signal, not yet a completed
            # financial transition — recorded via the caller's existing
            # audit-only path (event_processor §6b), nothing to reconcile yet.
            return ReconciliationOutcome(ok=True, mismatch=False, lifecycle_status=payment.lifecycle_status,
                                          reconciliation_status=payment.reconciliation_status or "UNVERIFIED",
                                          reason="NOT_APPLICABLE")
        return _refund_transition(db, payment, normalized, event_id=event_id,
                                   recovery_case_id=recovery_case_id)

    if event_type.startswith("payment.dispute."):
        return _dispute_transition(db, payment, normalized, event_id=event_id,
                                    recovery_case_id=recovery_case_id)

    target = TRANSITION_MAP.get(event_type)
    if target is None:
        return ReconciliationOutcome(ok=True, mismatch=False, lifecycle_status=payment.lifecycle_status,
                                      reconciliation_status=payment.reconciliation_status or "UNVERIFIED",
                                      reason="NOT_APPLICABLE")

    prior_status = payment.lifecycle_status
    if prior_status == target:
        # Same event TYPE reaching the state it's already in, via a genuinely
        # new (non-duplicate) event id — Razorpay's own docs describe
        # at-least-once, possibly-reordered webhook delivery, so a second
        # payment.captured for an already-CAPTURED payment is expected
        # benign redundancy, not a fabricated re-application: no field is
        # mutated, but it IS recorded so it's never silently invisible.
        _audit(db, payment, "DUPLICATE_FINANCIAL_TRANSITION_IGNORED",
               f"Redundant {event_type} for payment {payment.razorpay_payment_id} "
               f"already in state {target} — ignored, no state change.",
               {"source_event_id": event_id, "event_type": event_type},
               recovery_case_id=recovery_case_id)
        return ReconciliationOutcome(ok=True, mismatch=False, lifecycle_status=prior_status,
                                      reconciliation_status=payment.reconciliation_status or "IN_SYNC",
                                      reason="DUPLICATE_NOOP")

    allowed = ALLOWED_TRANSITIONS.get(prior_status, set())
    if target not in allowed:
        return _mismatch(db, payment, expected=prior_status, observed=target,
                          provider="razorpay", identifier=identifier,
                          reason="INVALID_TRANSITION", event_id=event_id,
                          recovery_case_id=recovery_case_id)

    event_amount_paise = normalized.get("amount_paise")
    if event_amount_paise is not None and int(event_amount_paise) != int(payment.amount_paise or 0):
        return _mismatch(db, payment, expected=payment.amount_paise, observed=event_amount_paise,
                          provider="razorpay", identifier=identifier,
                          reason="AMOUNT_MISMATCH", event_id=event_id,
                          recovery_case_id=recovery_case_id)

    payment.lifecycle_status = target
    payment.reconciliation_status = "IN_SYNC"
    audit_action = _AUDIT_ACTION_FOR_STATUS.get(target, "PAYMENT_STATE_CHANGED")
    _audit(db, payment, audit_action,
           f"Payment {payment.razorpay_payment_id} lifecycle state: {prior_status or 'NEW'} -> {target}.",
           {"source_event_id": event_id, "prior_status": prior_status, "new_status": target},
           recovery_case_id=recovery_case_id)
    return ReconciliationOutcome(ok=True, mismatch=False, lifecycle_status=target,
                                  reconciliation_status="IN_SYNC", reason="OK")
