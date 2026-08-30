"""
RECON OS — Phase 3: Authoritative Reconciliation

`reconcile_action(db, action_id)` asks Razorpay directly
(GET /v1/payment_links/{id}) whether the payment link was actually paid, and —
only if Razorpay reports `status == "paid"` with the full amount — marks the
action RECOVERED via the same validated `apply_recovery()` used by the webhook.

This makes a real recovery confirmable WITHOUT a public webhook: complete the
test payment on the Razorpay checkout page, then reconcile.

It never fakes anything: if Razorpay does not report the link as paid, the
action stays PENDING (or becomes PARTIAL / EXPIRED / CANCELLED).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from integrations.razorpay.adapter import get_razorpay_adapter
from models.recovery_action import RecoveryAction
from services.actions.common import audit_action
from services.actions.verification import apply_recovery, mark_link_terminal

logger = logging.getLogger("recon.services.actions.reconcile")


@dataclass
class ReconcileResult:
    ok: bool                       # True only when the action is now RECOVERED
    recovered: bool
    partial: bool
    razorpay_status: Optional[str]
    amount_paid: Optional[Decimal]
    message: str
    action: RecoveryAction


def reconcile_action(db: Session, action_id) -> ReconcileResult:
    action = db.query(RecoveryAction).filter(RecoveryAction.id == action_id).first()
    if action is None:
        raise ValueError(f"Recovery action {action_id} not found")

    def result(ok, recovered, partial, status, paid, msg):
        db.commit()
        db.refresh(action)
        return ReconcileResult(ok=ok, recovered=recovered, partial=partial,
                               razorpay_status=status, amount_paid=paid,
                               message=msg, action=action)

    # Already settled — nothing to do
    if (action.outcome or "").upper() == "RECOVERED":
        return result(True, True, False, action.provider_status, action.recovered_amount,
                      "Already recovered.")

    if (action.status or "").upper() != "EXECUTED" or not action.provider_action_id:
        return result(False, False, False, None, None,
                      f"Action is {action.status}/{action.outcome} — no payment link to reconcile.")

    adapter = get_razorpay_adapter()
    audit_action(db, action, "RECON_ENGINE", "RECONCILE_STARTED",
                 f"Reconciling {action.reference_id} against Razorpay "
                 f"(GET /payment_links/{action.provider_action_id})")

    res = adapter.get_payment_link(action.provider_action_id)
    if not res.ok:
        audit_action(db, action, "RAZORPAY_ADAPTER", "RECONCILE_FAILED",
                     f"Razorpay status check failed: {res.error_code} — {res.error_message}",
                     {"error_code": res.error_code})
        return result(False, False, False, None, None,
                      f"Razorpay status check failed: {res.error_code}.")

    status = (res.status or "").lower()
    paid_paise = int(res.amount_paid_paise or 0)
    expected_paise = int(action.amount_paise or 0)
    src = f"reconcile:{action.provider_action_id}:{datetime.now(timezone.utc).isoformat()}"

    audit_action(db, action, "RAZORPAY_ADAPTER", "RECONCILE_STATUS",
                 f"Razorpay reports payment_link.status='{status}', "
                 f"amount_paid={paid_paise} / expected={expected_paise}",
                 {"razorpay_status": status, "amount_paid_paise": paid_paise,
                  "amount_expected_paise": expected_paise,
                  "payments": res.payments})

    if status in ("expired", "cancelled"):
        mark_link_terminal(db, action, status, src)
        return result(False, False, False, status, None,
                      f"Payment link is {status} — recovery not completed.")

    if status == "paid" or paid_paise > 0:
        # With accept_partial=false a link only reaches status "paid" on FULL
        # payment; "partially_paid" carries a smaller amount_paid. Trust the
        # amount Razorpay reports; if status=="paid" but amount_paid is absent,
        # fall back to the expected amount.
        effective_paid = paid_paise if paid_paise > 0 else (
            expected_paise if status == "paid" else 0
        )
        # apply_recovery enforces the FULL-amount rule: >= expected -> RECOVERED,
        # anything short -> PARTIAL (case NOT resolved).
        apply_recovery(
            db, action,
            amount_paid_paise=effective_paid,
            currency=res.currency,
            source_event_id=src,
            provider_status=status or "paid",
            simulated=False,
        )
        db.flush()
        db.refresh(action)
        if (action.outcome or "").upper() == "RECOVERED":
            return result(True, True, False, status,
                          action.recovered_amount,
                          f"Razorpay confirms the payment link is paid — recovered "
                          f"{action.currency} {action.recovered_amount}.")
        if (action.outcome or "").upper() == "PARTIAL":
            return result(False, False, True, status,
                          (Decimal(paid_paise) / 100).quantize(Decimal("0.01")),
                          "Partial payment only — case NOT resolved.")
        return result(False, False, False, status, None,
                      "Payment signal did not pass validation — see audit trail.")

    # created / not paid yet
    return result(False, False, False, status, None,
                  f"Payment not completed yet (Razorpay status: {status or 'created'}).")
