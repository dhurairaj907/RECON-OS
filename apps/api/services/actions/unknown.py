"""
RECON OS — Phase 4: Resolving an UNKNOWN action outcome  (SAFETY-CRITICAL)

An action reaches outcome=UNKNOWN only when a Razorpay CREATE call timed out —
RECON genuinely does not know whether the Payment Link was created on
Razorpay's side. This module is the ONLY way an UNKNOWN action is ever
resolved, and it never guesses: it asks Razorpay directly (searching recent
Payment Links for our deterministic `reference_id`) and changes state only
based on what Razorpay actually reports.

    FOUND on Razorpay    -> the create actually succeeded; adopt it as
                            EXECUTED/PENDING (no duplicate is ever created)
                            and let the normal reconcile/webhook path take it
                            from there.
    CONFIRMED not found  -> the create never reached Razorpay; safe to mark
                            FAILED now (a verified fact, not a guess) so a
                            policy-gated retry becomes possible.
    Verification itself
    is inconclusive      -> remains UNKNOWN. No blind retry, ever.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from integrations.razorpay.adapter import get_razorpay_adapter
from models.recovery_action import RecoveryAction
from services.actions.common import audit_action

logger = logging.getLogger("recon.services.actions.unknown")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def verify_unknown_action(db: Session, action_id) -> RecoveryAction:
    action = db.query(RecoveryAction).filter(RecoveryAction.id == action_id).first()
    if action is None:
        raise ValueError(f"Recovery action {action_id} not found")

    if (action.outcome or "").upper() != "UNKNOWN":
        logger.info("verify-unknown called on %s which is not UNKNOWN (%s/%s) — no-op",
                    action.reference_id, action.status, action.outcome)
        return action

    adapter = get_razorpay_adapter()
    audit_action(db, action, "RECON_ENGINE", "UNKNOWN_VERIFICATION_STARTED",
                 f"Verifying ambiguous outcome for {action.reference_id} directly with "
                 f"Razorpay before allowing any retry.")
    db.commit()

    res = adapter.find_payment_link_by_reference(action.reference_id)

    if res.ok:
        # The create actually succeeded despite the client-side timeout.
        # Adopt the real result in place — this is NOT a new action, and no
        # duplicate Payment Link is created.
        action.status = "EXECUTED"
        action.outcome = "PENDING"
        action.executed_at = action.executed_at or _now()
        action.provider_action_id = res.payment_link_id
        action.provider_status = res.status
        action.payment_link_url = res.short_url
        action.error_code = None
        action.error_message = None
        audit_action(db, action, "RAZORPAY_ADAPTER", "UNKNOWN_RESOLVED_SUCCESS",
                     f"Verified with Razorpay: Payment Link {res.payment_link_id} for "
                     f"{action.reference_id} WAS created despite the earlier timeout — "
                     f"resolved from ambiguity, no duplicate created. Status now "
                     f"EXECUTED/PENDING.",
                     {"payment_link_id": res.payment_link_id, "razorpay_status": res.status})
        db.commit()
        db.refresh(action)
        return action

    if res.error_code == "RAZORPAY_NOT_FOUND":
        # Confirmed absent — this is now a verified fact, safe to treat as a
        # genuine failure and unlock a policy-gated retry.
        action.status = "FAILED"
        action.outcome = "FAILED"
        action.error_code = "RAZORPAY_TIMEOUT_VERIFIED_NOT_CREATED"
        action.error_message = ("Verified with Razorpay: no Payment Link exists for this "
                                "reference id. The original create request never reached "
                                "Razorpay. A new attempt is safe and remains policy-gated.")
        audit_action(db, action, "RAZORPAY_ADAPTER", "UNKNOWN_RESOLVED_FAILED",
                     f"Verified with Razorpay: {action.reference_id} was never created — "
                     f"marking FAILED. A fresh attempt is now policy-gated, not blind.",
                     {"error_code": action.error_code})
        db.commit()
        db.refresh(action)
        return action

    # Verification itself was inconclusive (timeout / rate-limit / api error) —
    # remain UNKNOWN. Never guess.
    audit_action(db, action, "RAZORPAY_ADAPTER", "UNKNOWN_VERIFICATION_INCONCLUSIVE",
                 f"Could not verify {action.reference_id}: {res.error_code} — "
                 f"{res.error_message}. Remaining UNKNOWN; no state change.",
                 {"error_code": res.error_code})
    db.commit()
    db.refresh(action)
    logger.warning("Verification of %s remained inconclusive (%s)",
                   action.reference_id, res.error_code)
    return action
