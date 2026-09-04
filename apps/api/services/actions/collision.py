"""
RECON OS — Phase 3: Razorpay Payment Link reference-id collision handling
(SAFETY-CRITICAL)

Root cause this module fixes: execute_action() calls RazorpayAdapter.
create_payment_link() with a deterministic reference_id (see
services/actions/common.py::reference_id_for) — e.g. RECON-RC10006-ACT001.
Razorpay enforces reference_id uniqueness on its own side; RECON's
RecoveryAction.reference_id column is also unique at the DB level. A
"reference_id already exists" rejection from Razorpay (confirmed in
production: RAZORPAY_BAD_REQUEST, "payment link with given reference_id: ...
already exists") therefore means exactly one of two things:

  1. An EARLIER execution attempt for THIS SAME action actually succeeded at
     Razorpay, but RECON never durably recorded the result locally (e.g. a
     process crash/restart between the Razorpay response and our commit, or
     any failure classified as a generic error rather than the narrower
     client-side-timeout case unknown.py already handles). The existing
     Payment Link genuinely belongs to this action — reconcile with it,
     using the exact same validated transitions verification.py/reconcile.py
     already use everywhere else. NEVER create a second Payment Link for it.

  2. The existing link at that reference cannot be verified as belonging to
     this action (not found in Razorpay's recent list, or any other
     inconclusive result). Never adopt an unverified link and never silently
     overwrite it — generate a new, deterministic, collision-safe
     reference_id, preserve the original in audit metadata, and let the
     caller (execute_action) attempt a fresh create with the new reference.

This module never calls Razorpay to create anything — it only searches
(read-only) and re-derives a new reference string. The actual create retry
stays in executor.py, which already owns the full execution flow.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from integrations.razorpay.adapter import get_razorpay_adapter
from models.recovery_action import RecoveryAction
from services.actions.common import audit_action
from services.actions.reconcile import dispatch_payment_link_status

logger = logging.getLogger("recon.services.actions.collision")

_REGEN_SUFFIX = re.compile(r"^(?P<base>.+)-R(?P<n>\d+)$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_reference_collision(error_message: str | None) -> bool:
    """
    Detects Razorpay's specific "reference_id already exists" rejection —
    confirmed live in production: RAZORPAY_BAD_REQUEST, description "payment
    link with given reference_id: ... already exists. Please create a
    payment link with a different reference_id." Deliberately a narrow text
    match (not every RAZORPAY_BAD_REQUEST) so a genuine input error (bad
    amount, malformed email, etc.) is never misrouted into reconciliation.
    """
    if not error_message:
        return False
    m = error_message.lower()
    return "reference_id" in m and "already exists" in m


def generate_collision_safe_reference(current_reference_id: str) -> str:
    """
    Deterministic — reproducible purely from the current reference string,
    never random or time-seeded. Appending a monotonic `-R{n}` suffix can
    never collide with the original (Razorpay + RECON both already enforce
    that one is unique) or with another action's reference (every action's
    base reference is itself unique, derived from the globally-unique
    RecoveryCase.case_number).
    """
    m = _REGEN_SUFFIX.match(current_reference_id)
    if m:
        return f"{m.group('base')}-R{int(m.group('n')) + 1}"
    return f"{current_reference_id}-R1"


@dataclass
class CollisionOutcome:
    reconciled: bool   # True: action now reflects a real, verified Payment Link
                        # state — the caller must NOT attempt to create a new one.
    action: RecoveryAction


def reconcile_collision(db: Session, action: RecoveryAction) -> CollisionOutcome:
    """
    Called only after Razorpay has just rejected a create with a reference-id
    collision (see is_reference_collision). Searches Razorpay for the
    existing link and either reconciles this action with it (reconciled=True)
    or regenerates action.reference_id for the caller to retry with
    (reconciled=False) — never guesses, never overwrites another action's
    link.
    """
    adapter = get_razorpay_adapter()
    original_reference = action.reference_id

    audit_action(
        db, action, "RAZORPAY_ADAPTER", "PAYMENT_LINK_REFERENCE_COLLISION",
        f"Razorpay rejected Payment Link creation for {original_reference}: a "
        f"payment link with this exact reference_id already exists. Searching "
        f"Razorpay for the existing link before deciding whether to reconcile "
        f"or regenerate — never guessing and never creating a duplicate.",
        {"reference_id": original_reference},
    )
    db.commit()

    res = adapter.find_payment_link_by_reference(original_reference)

    if res.ok and res.reference_id == original_reference:
        # Verified: this Payment Link was created under RECON's own
        # deterministic reference for THIS action — safe to adopt.
        audit_action(
            db, action, "RAZORPAY_ADAPTER", "PAYMENT_LINK_REFERENCE_RECONCILED",
            f"Found the existing Payment Link {res.payment_link_id} for "
            f"{original_reference} at Razorpay, verified it matches this "
            f"action's reference — reconciling instead of creating a "
            f"duplicate. Razorpay status: {res.status}.",
            {"payment_link_id": res.payment_link_id, "razorpay_status": res.status},
        )
        action.status = "EXECUTED"
        action.outcome = "PENDING"
        action.executed_at = action.executed_at or _now()
        action.provider_action_id = res.payment_link_id
        action.provider_status = res.status
        action.payment_link_url = res.short_url
        action.error_code = None
        action.error_message = None
        db.commit()
        db.refresh(action)

        # Reuses the SAME validated apply_recovery()/mark_link_terminal()
        # transitions the webhook and manual-reconcile paths use — never a
        # bespoke "mark recovered" write here. If Razorpay already reports
        # this link as paid, this is what upgrades outcome to RECOVERED
        # (test case E) instead of leaving it at PENDING.
        dispatch_payment_link_status(
            db, action, res, f"collision-reconcile:{res.payment_link_id}"
        )
        db.commit()
        db.refresh(action)
        return CollisionOutcome(reconciled=True, action=action)

    # Not found (or, defensively, a reference mismatch that should never
    # happen given find_payment_link_by_reference's own exact-match filter)
    # — never adopt an unverified link, never overwrite it.
    new_reference = generate_collision_safe_reference(original_reference)
    audit_action(
        db, action, "ACTION_ENGINE", "PAYMENT_LINK_REFERENCE_REGENERATED",
        f"Could not verify an existing, matching Payment Link for "
        f"{original_reference} ({res.error_code or 'not found'}) — "
        f"regenerating a new, collision-safe reference id ({new_reference}) "
        f"rather than guessing or overwriting a link that may belong to "
        f"another action.",
        {"original_reference_id": original_reference,
         "new_reference_id": new_reference,
         "lookup_error_code": res.error_code},
    )
    action.reference_id = new_reference
    db.commit()
    db.refresh(action)
    return CollisionOutcome(reconciled=False, action=action)
