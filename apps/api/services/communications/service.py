"""
RECON OS — Phase 5: Recovery Communication Decision + Send  (SAFETY-CRITICAL)

    Strategy -> Policy Engine -> COMMUNICATION DECISION -> approval if
    required -> Provider -> Customer

`decide_communication()` NEVER re-implements or bypasses the Policy Engine or
the human-approval mechanism — it only reads the already-adjudicated
`CaseIntelligence.policy_verdict` and `RecoveryAction` state (status,
blocked_reason, human_decision, outcome) that the real Policy/Action Engine
already produced. A REJECTED verdict or a human rejection blocks every
message type. A NEEDS_APPROVAL action not yet approved blocks every
link-bearing message type. This is deliberately the SAME approval outcome
actions already use — not a second execution/approval architecture.

`send_communication()` is the only place that ever calls a provider. It is
never reachable from AI/strategy code — only from the router below, which is
itself role-gated (OPERATOR/ADMIN).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from models.audit_log import AuditLog
from models.case_intelligence import CaseIntelligence
from models.communication import Communication
from models.customer import Customer
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from services.communications.providers import get_communication_provider
from services.communications.templates import render_template

logger = logging.getLogger("recon.services.communications")

LINK_MESSAGE_TYPES = {"PAYMENT_RECOVERY", "PAYMENT_LINK_CREATED", "RECOVERY_REMINDER"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CommunicationDecision:
    eligible: bool
    reason: str
    skipped_reason: Optional[str] = None   # matches Communication.skipped_reason vocabulary


def _latest_intelligence(db: Session, case_id) -> CaseIntelligence | None:
    return (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id == case_id)
        .order_by(CaseIntelligence.version.desc())
        .first()
    )


def decide_communication(
    message_type: str, *, case: RecoveryCase, action: RecoveryAction | None, intelligence: CaseIntelligence | None,
) -> CommunicationDecision:
    policy_verdict = (intelligence.policy_verdict or "") if intelligence else ""
    if policy_verdict == "REJECTED":
        return CommunicationDecision(False, "Policy Engine rejected this case — no customer communication is sent.", "NOT_ELIGIBLE")

    if message_type == "PAYMENT_FAILED":
        if intelligence is None:
            return CommunicationDecision(False, "Case has not been analyzed yet.", "NOT_ELIGIBLE")
        return CommunicationDecision(True, "Eligible.")

    if message_type == "PAYMENT_RECOVERED":
        if action is None or (action.outcome or "").upper() != "RECOVERED":
            return CommunicationDecision(False, "This case has not been verified as recovered yet.", "NOT_ELIGIBLE")
        return CommunicationDecision(True, "Eligible.")

    # PAYMENT_RECOVERY / PAYMENT_LINK_CREATED / RECOVERY_REMINDER — all require
    # a real, live payment link, exactly the same gate execute_action itself enforces.
    if action is None:
        return CommunicationDecision(False, "No recovery action exists for this case yet.", "NOT_ELIGIBLE")
    if (action.blocked_reason or "") == "HUMAN_REJECTED" or action.human_decision == "REJECTED":
        return CommunicationDecision(False, "This action was rejected by a human reviewer.", "NOT_ELIGIBLE")
    if action.status == "BLOCKED" and (action.blocked_reason or "") == "NEEDS_APPROVAL" and action.human_decision != "APPROVED":
        return CommunicationDecision(False, "This action still requires human approval before a message can be sent.", "REQUIRES_APPROVAL")
    if (action.outcome or "").upper() == "UNKNOWN":
        return CommunicationDecision(False, "Outcome is UNKNOWN pending verification — no message sent.", "NOT_ELIGIBLE")
    if action.status != "EXECUTED" or not action.payment_link_url:
        return CommunicationDecision(False, "No live payment link exists for this case yet.", "NOT_ELIGIBLE")
    return CommunicationDecision(True, "Eligible.")


def _resolve_contact(customer: Customer | None, channel: str) -> Optional[str]:
    if customer is None:
        return None
    if channel == "EMAIL":
        return customer.email or None
    return customer.phone or None   # SMS and WHATSAPP both use the phone number on file


def _is_opted_out(customer: Customer | None, channel: str) -> bool:
    if customer is None or not customer.opted_out_channels:
        return False
    return channel in {c.strip().upper() for c in customer.opted_out_channels.split(",") if c.strip()}


def _audit(db: Session, merchant_id, case_id, event: str, detail: str, metadata: dict) -> None:
    db.add(AuditLog(merchant_id=merchant_id, recovery_case_id=case_id, actor="COMMUNICATION_ENGINE",
                    action=event, detail=detail, metadata_json=metadata))


def _idempotency_key(case: RecoveryCase, action: RecoveryAction | None, message_type: str) -> str:
    """Deterministic — derived only from existing identifiers, never a
    timestamp or random UUID, so the SAME logical recovery event always
    produces the SAME key regardless of how many times it's evaluated."""
    return f"{case.id}:{action.id if action else 'none'}:{message_type}"


def _skip(db: Session, *, merchant_id, case, action, customer, channel, message_type, status, skipped_reason, reason) -> Communication:
    comm = Communication(
        merchant_id=merchant_id, recovery_case_id=case.id,
        recovery_action_id=action.id if action else None,
        customer_id=customer.id if customer else None,
        channel=channel, message_type=message_type, status=status, skipped_reason=skipped_reason,
        error_message=reason, idempotency_key=_idempotency_key(case, action, message_type),
    )
    db.add(comm)
    db.commit()
    db.refresh(comm)
    _audit(db, merchant_id, case.id, "COMMUNICATION_SKIPPED",
          f"{channel}/{message_type} not sent for {case.case_number}: {reason}",
          {"channel": channel, "message_type": message_type, "skipped_reason": skipped_reason})
    db.commit()
    return comm


def send_communication(
    db: Session, *, merchant_id, case: RecoveryCase, channel: str, message_type: str, decided_by: str = "OPERATOR",
) -> Communication:
    """
    The ONLY function that ever calls a communication provider. Re-derives
    eligibility fresh from current case/action/intelligence state — never
    trusts a stored or caller-supplied "approved" flag.
    """
    action = (
        db.query(RecoveryAction)
        .filter(RecoveryAction.recovery_case_id == case.id)
        .order_by(RecoveryAction.created_at.desc())
        .first()
    )
    intelligence = _latest_intelligence(db, case.id)
    customer = db.query(Customer).filter(Customer.id == case.customer_id).first() if case.customer_id else None

    decision = decide_communication(message_type, case=case, action=action, intelligence=intelligence)
    if not decision.eligible:
        return _skip(db, merchant_id=merchant_id, case=case, action=action, customer=customer,
                    channel=channel, message_type=message_type, status="SKIPPED",
                    skipped_reason=decision.skipped_reason, reason=decision.reason)

    contact = _resolve_contact(customer, channel)
    if not contact:
        return _skip(db, merchant_id=merchant_id, case=case, action=action, customer=customer,
                    channel=channel, message_type=message_type, status="SKIPPED",
                    skipped_reason="NO_CONTACT_INFO",
                    reason=f"No {channel.lower()} contact information on file for this customer.")

    if _is_opted_out(customer, channel):
        return _skip(db, merchant_id=merchant_id, case=case, action=action, customer=customer,
                    channel=channel, message_type=message_type, status="OPTED_OUT",
                    skipped_reason="OPTED_OUT",
                    reason=f"Customer has opted out of {channel}.")

    # Duplicate prevention — the SAME logical message (same case, same action
    # or lack of one, same message type) should never be sent twice while a
    # prior attempt is still outstanding/succeeded. Keyed identically to the
    # idempotency_key stored on every row, so a caller retry, a duplicate
    # webhook-triggered send, or a second automation pass all land on the
    # exact same check — not three separate ones.
    idem_key = _idempotency_key(case, action, message_type)
    dup = (
        db.query(Communication)
        .filter(
            Communication.idempotency_key == idem_key,
            Communication.status.in_(["SENT", "DELIVERED", "QUEUED", "SENDING"]),
        )
        .first()
    )
    if dup is not None:
        return _skip(db, merchant_id=merchant_id, case=case, action=action, customer=customer,
                    channel=channel, message_type=message_type, status="SKIPPED",
                    skipped_reason="DUPLICATE",
                    reason=f"A {message_type} message for this case was already {dup.status.lower()}.")

    # Lifetime cap on this case, independent of the per-day pace limit below —
    # bounds the WHOLE sequence, not just how fast it can run.
    if settings.MAX_COMMUNICATIONS_PER_CASE:
        total_sent = (
            db.query(Communication)
            .filter(Communication.recovery_case_id == case.id,
                    Communication.status.in_(["SENT", "DELIVERED"]))
            .count()
        )
        if total_sent >= settings.MAX_COMMUNICATIONS_PER_CASE:
            return _skip(db, merchant_id=merchant_id, case=case, action=action, customer=customer,
                        channel=channel, message_type=message_type, status="SKIPPED",
                        skipped_reason="CASE_LIMIT_REACHED",
                        reason=f"Maximum communications for this case "
                               f"({settings.MAX_COMMUNICATIONS_PER_CASE}) already reached.")

    # Per-customer daily cap — bounds a customer's TOTAL exposure across every
    # one of their cases, not just this one.
    if customer is not None and settings.MAX_COMMUNICATIONS_PER_CUSTOMER_PER_DAY:
        cutoff_customer = _now() - timedelta(hours=24)
        recent_customer = (
            db.query(Communication)
            .filter(Communication.customer_id == customer.id,
                    Communication.created_at >= cutoff_customer,
                    Communication.status.in_(["SENT", "DELIVERED"]))
            .count()
        )
        if recent_customer >= settings.MAX_COMMUNICATIONS_PER_CUSTOMER_PER_DAY:
            return _skip(db, merchant_id=merchant_id, case=case, action=action, customer=customer,
                        channel=channel, message_type=message_type, status="SKIPPED",
                        skipped_reason="CUSTOMER_DAILY_LIMIT_REACHED",
                        reason=f"This customer has already reached the daily communication limit "
                               f"({settings.MAX_COMMUNICATIONS_PER_CUSTOMER_PER_DAY}) across their cases.")

    # Per-case rate limit — bounds recovery-message loops.
    cutoff = _now() - timedelta(hours=24)
    recent = (
        db.query(Communication)
        .filter(Communication.recovery_case_id == case.id, Communication.created_at >= cutoff)
        .count()
    )
    if recent >= settings.COMMUNICATION_RATE_LIMIT_PER_CASE_PER_DAY:
        return _skip(db, merchant_id=merchant_id, case=case, action=action, customer=customer,
                    channel=channel, message_type=message_type, status="SKIPPED",
                    skipped_reason="RATE_LIMITED",
                    reason=f"Rate limit reached ({settings.COMMUNICATION_RATE_LIMIT_PER_CASE_PER_DAY}/day) for this case.")

    amount = Decimal(action.amount) if (action and action.amount is not None) else Decimal(case.amount_at_risk or 0)
    currency = (action.currency if action else case.currency) or "INR"
    rendered = render_template(
        message_type,
        customer_name=(customer.name if customer else None),
        amount=f"{amount:.2f}", currency=currency,
        organization_name=merchant_id and _merchant_name(db, merchant_id),
        payment_link=(action.payment_link_url if action else None),
    )
    # WhatsApp only: a real provider needs a pre-approved template identifier,
    # never raw AI-generated or ad hoc text — see providers.WebhookWhatsAppProvider.
    template_id = settings.resolved_whatsapp_template(message_type) if channel == "WHATSAPP" else None

    comm = Communication(
        merchant_id=merchant_id, recovery_case_id=case.id,
        recovery_action_id=action.id if action else None,
        customer_id=customer.id if customer else None,
        channel=channel, message_type=message_type, status="SENDING",
        recipient=contact, subject=rendered.subject, body=rendered.body,
        idempotency_key=idem_key,
    )
    db.add(comm)
    db.commit()
    db.refresh(comm)

    provider = get_communication_provider(channel)
    result = provider.send(to=contact, subject=rendered.subject, body=rendered.body,
                           template_id=template_id, template_vars=rendered.variables)

    if result.ok:
        comm.status = result.status
        comm.provider = result.provider
        comm.provider_message_id = result.provider_message_id
        comm.sent_at = _now()
        _audit(db, merchant_id, case.id, "COMMUNICATION_SENT",
              f"{channel}/{message_type} sent for {case.case_number} via {result.provider}",
              {"channel": channel, "message_type": message_type, "provider": result.provider})
    else:
        comm.status = "FAILED"
        comm.provider = result.provider
        comm.error_code = result.error_code
        comm.error_message = result.error_message
        _audit(db, merchant_id, case.id, "COMMUNICATION_FAILED",
              f"{channel}/{message_type} failed for {case.case_number}: {result.error_code}",
              {"channel": channel, "message_type": message_type, "error_code": result.error_code})

    db.commit()
    db.refresh(comm)
    return comm


def _merchant_name(db: Session, merchant_id) -> str:
    from models.merchant import Merchant
    m = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    return m.name if m else ""
