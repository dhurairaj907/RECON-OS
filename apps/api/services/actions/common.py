"""
RECON OS — Phase 3 action helpers: deterministic keys, eligibility, UI state, audit.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from models.audit_log import AuditLog
from models.recovery_action import RecoveryAction

# Strategy intents that translate to an executable CREATE_PAYMENT_LINK action.
# A failed Razorpay payment cannot be re-charged via API, so every "retry"-style
# recommendation is realised as a Payment Link the customer chooses to pay.
PAYMENT_LINK_ELIGIBLE_STRATEGIES = {"RETRY_NOW", "RETRY_DELAYED", "SEND_PAYMENT_LINK"}

TERMINAL_CASE_STATUSES = {"RESOLVED", "CLOSED"}


def reference_id_for(case_number: str, action_version: int = 1) -> str:
    """Deterministic, unique reference id — e.g. RECON-RC10001-ACT001."""
    slug = (case_number or "RC").replace("-", "").upper()
    return f"RECON-{slug}-ACT{action_version:03d}"


def idempotency_key_for(recovery_case_id, action_type: str, action_version: int = 1) -> str:
    return f"{recovery_case_id}:{action_type}:{action_version}"


def to_paise(amount: Decimal) -> int:
    """₹4,999.00 -> 499900. Deterministic, no float error."""
    q = (Decimal(amount) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(q)


def ui_state(action: RecoveryAction) -> str:
    status = (action.status or "").upper()
    outcome = (action.outcome or "").upper()
    if outcome == "UNKNOWN":
        # Ambiguous provider outcome (e.g. a create-side timeout) takes
        # priority over status — never render this as FAILED or as a normal
        # in-progress state. Resolved only by explicit verification.
        return "UNKNOWN"
    if status == "BLOCKED":
        if (action.blocked_reason or "") == "NEEDS_APPROVAL":
            return "NEEDS_APPROVAL"
        return "BLOCKED"
    if status == "FAILED":
        return "FAILED"
    if status == "PROPOSED":
        return "READY"
    if status == "APPROVED":
        return "APPROVED"
    if status == "EXECUTING":
        return "EXECUTING"
    if status == "EXECUTED":
        if outcome == "RECOVERED":
            return "RECOVERED"
        if outcome in ("PARTIAL", "FAILED", "EXPIRED", "CANCELLED"):
            return outcome
        return "WAITING_FOR_PAYMENT"
    return status or "READY"


def audit_action(db, action: RecoveryAction, actor: str, event: str, detail: str,
                 metadata: dict | None = None):
    meta = {
        "action_id": str(action.id),
        "action_type": action.action_type,
        "reference_id": action.reference_id,
    }
    if metadata:
        meta.update(metadata)
    db.add(AuditLog(
        merchant_id=action.merchant_id,
        recovery_case_id=action.recovery_case_id,
        actor=actor,
        action=event,
        detail=detail,
        metadata_json=meta,
    ))
