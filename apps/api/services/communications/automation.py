"""
RECON OS — Phase 7: Controlled Automatic Recovery Communication  (SAFETY-CRITICAL)

Hooks into REAL, already-existing state transitions — action execution and
outcome verification — never a new scheduler/worker/queue (RECON OS has none
in this phase). Every hook is a strict no-op unless
settings.AUTOMATIC_COMMUNICATIONS_ENABLED, and every send still goes through
the SAME send_communication()/decide_communication() the manual endpoint
uses — there is exactly one path that ever reaches a provider, and this
module never re-implements or shortcuts it. A failure anywhere here is
caught and logged; it can never break action execution or payment
verification, the safety-critical flows these hooks attach to.

Minimal, bounded sequence:
    action EXECUTED (Payment Link created) -> auto PAYMENT_RECOVERY message
    outcome verified RECOVERED             -> auto PAYMENT_RECOVERED thank-you
    evaluate_reminder_sequence()           -> at most one RECOVERY_REMINDER,
        gated on MIN_HOURS_BETWEEN_MESSAGES / MAX_COMMUNICATIONS_PER_CASE and
        every stop condition below. This step is exposed as an explicit
        operator/automation entrypoint (see
        routers/communications.py:evaluate_case_communication_sequence)
        rather than fired by a background job, since none exists — an
        external scheduler (cron, a queue worker) can call it on a cadence.

Channel selection reads Phase 6's `communication_channel` prediction already
persisted on the case's latest CaseIntelligence row (never recomputed,
retrained, or trusted blindly) and falls back to EMAIL. This is exactly the
"AI recommends, deterministic controls decide" shape the phase requires:
send_communication/_available_channels still independently re-verify contact
availability, opt-outs, policy, and approval before anything is sent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from models.case_intelligence import CaseIntelligence
from models.communication import Communication
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from services.communications.service import send_communication

logger = logging.getLogger("recon.services.communications.automation")

_CLOSED_CASE_STATUSES = ("RESOLVED", "CLOSED")
_VALID_CHANNELS = ("EMAIL", "SMS", "WHATSAPP")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _latest_intelligence(db: Session, case_id) -> Optional[CaseIntelligence]:
    return (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id == case_id)
        .order_by(CaseIntelligence.version.desc())
        .first()
    )


def ai_recommendation(db: Session, case: RecoveryCase) -> dict:
    """
    Assembles the {strategy, channel, confidence, expected_recovery_value,
    reason} shape the phase asks for, purely from Phase 6 predictions ALREADY
    persisted on this case's latest intelligence run (see
    ai/inference/service.py + services/intelligence/orchestrator.py) — never
    recomputed here, never a new model. Every field is None if that
    prediction wasn't available (a model not yet trained, or no intelligence
    run yet) — never fabricated. Purely advisory / for audit context; the
    Policy Engine and send_communication's own checks are what actually
    decide whether anything is sent.
    """
    ci = _latest_intelligence(db, case.id)
    preds = (ci.ml_predictions_json or {}) if ci else {}
    strategy_ranking = ((preds.get("strategy_ranking") or {}).get("ranking")) or []
    channel_ranking = ((preds.get("communication_channel") or {}).get("ranking")) or []
    erv_ranking = ((preds.get("expected_recovery_value") or {}).get("ranking")) or []
    top_strategy = strategy_ranking[0] if strategy_ranking else None
    top_channel = channel_ranking[0] if channel_ranking else None
    top_value = erv_ranking[0] if erv_ranking else None
    return {
        "strategy": top_strategy.get("strategy") if top_strategy else None,
        "channel": top_channel.get("channel") if top_channel else None,
        "confidence": top_strategy.get("score") if top_strategy else None,
        "expected_recovery_value": top_value.get("expected_recovery_value") if top_value else None,
        "reason": (
            "Derived from Phase 6 ML predictions already attached to this case's latest "
            "intelligence run — advisory only. The Policy Engine and "
            "send_communication()'s own eligibility/contact/opt-out/limit checks are "
            "authoritative and are re-run independently regardless of this recommendation."
        ) if ci else "No intelligence run exists yet for this case — no AI recommendation available.",
    }


def _pick_channel(db: Session, case: RecoveryCase) -> str:
    rec = ai_recommendation(db, case)
    channel = rec.get("channel")
    return channel if channel in _VALID_CHANNELS else "EMAIL"


def _audit_recommendation(db: Session, merchant_id, case: RecoveryCase, rec: dict, trigger: str) -> None:
    from models.audit_log import AuditLog
    db.add(AuditLog(
        merchant_id=merchant_id, recovery_case_id=case.id, actor="COMMUNICATION_AUTOMATION",
        action="AI_RECOMMENDATION_CONSIDERED",
        detail=f"Automatic communication ({trigger}) considered AI recommendation for "
               f"{case.case_number}: strategy={rec.get('strategy')} channel={rec.get('channel')}",
        metadata_json=rec,
    ))
    db.commit()


def _fan_out_to_all_channels(db: Session, *, merchant_id, case: RecoveryCase, message_type: str) -> list[Communication]:
    """
    Attempts EVERY real channel (EMAIL, SMS, WHATSAPP) for one automated
    recovery event — not just the AI's single top-ranked pick — matching a
    real merchant's expectation that an approved automated recovery reaches
    the customer on every channel actually available to them, not just one.

    Each channel goes through send_communication() independently and is
    wrapped in its own try/except: a failure or skip on one channel (no
    contact info, opted out, provider down) can NEVER prevent the others
    from being attempted, and can never abort the overall recovery. This is
    the exact same send_communication() a manual send uses — no new
    provider logic, no new eligibility rules; opt-out/contact-availability/
    policy/rate-limit/idempotency checks all run per channel exactly as they
    already do for a single manual send.
    """
    results: list[Communication] = []
    for channel in _VALID_CHANNELS:
        try:
            comm = send_communication(
                db, merchant_id=merchant_id, case=case, channel=channel,
                message_type=message_type, decided_by="AUTOMATION",
            )
            if comm is not None:
                results.append(comm)
        except Exception:
            logger.exception(
                "Automatic %s send failed for case %s (non-fatal — other channels still attempted)",
                channel, case.id,
            )
    return results


def on_action_executed(db: Session, *, merchant_id, case: RecoveryCase, action: RecoveryAction) -> list[Communication]:
    """Called right after the Action Engine sets an action EXECUTED (a real
    Payment Link now exists). Every safety check still lives in
    decide_communication()/send_communication(), re-run fresh here exactly as
    a manual send would be — this hook only decides WHEN to ask, never
    whether it's allowed. Fans out to every configured, eligible channel
    (see _fan_out_to_all_channels) rather than picking just one."""
    if not settings.AUTOMATIC_COMMUNICATIONS_ENABLED:
        return []
    try:
        rec = ai_recommendation(db, case)
        _audit_recommendation(db, merchant_id, case, rec, "post-execution")
    except Exception:
        logger.exception("Automatic post-execution AI recommendation lookup failed for case %s (non-fatal)", case.id)
    return _fan_out_to_all_channels(db, merchant_id=merchant_id, case=case, message_type="PAYMENT_RECOVERY")


def on_recovery_verified(db: Session, *, merchant_id, case: RecoveryCase, action: RecoveryAction) -> list[Communication]:
    """Called right after apply_recovery() marks an action RECOVERED.
    decide_communication() already requires a verified RECOVERED outcome for
    this message type, so this can never fire early or on a fabricated
    outcome. Fans out to every configured, eligible channel."""
    if not settings.AUTOMATIC_COMMUNICATIONS_ENABLED:
        return []
    return _fan_out_to_all_channels(db, merchant_id=merchant_id, case=case, message_type="PAYMENT_RECOVERED")




@dataclass
class SequenceDecision:
    sent: bool
    reason: str
    communication: Optional[Communication] = None


def _cancel(db: Session, *, merchant_id, case: RecoveryCase, action: Optional[RecoveryAction], reason: str) -> SequenceDecision:
    """Records a stopped CONTINUATION distinctly from a never-eligible
    attempt (SKIPPED) — useful, honest signal for future (Phase 8) training
    data: this wasn't rejected on arrival, a real in-flight sequence was
    explicitly called off by a stop condition."""
    comm = Communication(
        merchant_id=merchant_id, recovery_case_id=case.id,
        recovery_action_id=action.id if action else None,
        customer_id=case.customer_id, channel="EMAIL", message_type="RECOVERY_REMINDER",
        status="CANCELLED", skipped_reason="SEQUENCE_STOPPED", error_message=reason,
        idempotency_key=f"{case.id}:{action.id if action else 'none'}:RECOVERY_REMINDER:cancel:{_now().date()}",
    )
    db.add(comm)
    db.commit()
    db.refresh(comm)
    return SequenceDecision(False, reason, comm)


def evaluate_reminder_sequence(db: Session, *, merchant_id, case: RecoveryCase) -> SequenceDecision:
    """
    On-demand evaluation of the ONE follow-up reminder step in RECON's
    minimal safe sequence (payment-link message -> wait -> verify -> if still
    unpaid -> one reminder -> verify). Every stop condition below is checked
    explicitly and independently of send_communication's own checks (which
    still run too) — belt and braces, never a shortcut around them.
    """
    action = (
        db.query(RecoveryAction)
        .filter(RecoveryAction.recovery_case_id == case.id)
        .order_by(RecoveryAction.created_at.desc())
        .first()
    )

    if not settings.AUTOMATIC_COMMUNICATIONS_ENABLED:
        return SequenceDecision(False, "Automatic communications are disabled.")
    if (case.status or "").upper() in _CLOSED_CASE_STATUSES:
        return _cancel(db, merchant_id=merchant_id, case=case, action=action,
                       reason=f"Case is {case.status} — payment already recovered or case closed.")
    if action is None or action.status != "EXECUTED":
        return SequenceDecision(False, "No executed recovery action for this case yet.")
    outcome = (action.outcome or "").upper()
    if outcome == "RECOVERED":
        return _cancel(db, merchant_id=merchant_id, case=case, action=action,
                       reason="Payment already recovered — reminder sequence stopped.")
    if outcome in ("EXPIRED", "CANCELLED"):
        return _cancel(db, merchant_id=merchant_id, case=case, action=action,
                       reason=f"Payment link outcome is {outcome} — reminder sequence stopped.")
    if outcome == "UNKNOWN":
        return SequenceDecision(False, "Outcome is UNKNOWN pending verification — no reminder sent yet.")

    # Recovery Opportunity gate (reuses CaseIntelligence.prediction_band —
    # the same LOW/MEDIUM/HIGH dimension services/intelligence/prediction.py
    # already computes, never a duplicate classification). No repeated
    # follow-up for a case whose latest evidence says recovery is unlikely —
    # "maximize recoverable revenue, not maximize messages".
    latest_ci = _latest_intelligence(db, case.id)
    if latest_ci is not None and latest_ci.prediction_band == "LOW":
        return _cancel(db, merchant_id=merchant_id, case=case, action=action,
                       reason=f"Recovery opportunity is LOW (recovery_probability="
                              f"{float(latest_ci.recovery_probability or 0):.0%}) — automated follow-up "
                              f"pursuit stopped rather than sending a low-value reminder.")

    total_sent = (
        db.query(Communication)
        .filter(Communication.recovery_case_id == case.id, Communication.status.in_(["SENT", "DELIVERED"]))
        .count()
    )
    if total_sent == 0:
        return SequenceDecision(False, "No initial recovery message has been sent yet — nothing to follow up on.")
    if settings.MAX_COMMUNICATIONS_PER_CASE and total_sent >= settings.MAX_COMMUNICATIONS_PER_CASE:
        return _cancel(db, merchant_id=merchant_id, case=case, action=action,
                       reason=f"Maximum communications per case ({settings.MAX_COMMUNICATIONS_PER_CASE}) "
                              f"already reached.")

    last_sent = (
        db.query(Communication)
        .filter(Communication.recovery_case_id == case.id, Communication.status.in_(["SENT", "DELIVERED"]))
        .order_by(Communication.sent_at.desc())
        .first()
    )
    if last_sent and last_sent.sent_at:
        sent_at = last_sent.sent_at if last_sent.sent_at.tzinfo else last_sent.sent_at.replace(tzinfo=timezone.utc)
        elapsed_hours = (_now() - sent_at).total_seconds() / 3600.0
        if elapsed_hours < settings.MIN_HOURS_BETWEEN_MESSAGES:
            return SequenceDecision(
                False,
                f"Only {elapsed_hours:.1f}h since the last message — minimum "
                f"{settings.MIN_HOURS_BETWEEN_MESSAGES}h between messages not yet elapsed.",
            )

    rec = ai_recommendation(db, case)
    _audit_recommendation(db, merchant_id, case, rec, "reminder-sequence")
    channel = _pick_channel(db, case)
    try:
        comm = send_communication(
            db, merchant_id=merchant_id, case=case, channel=channel,
            message_type="RECOVERY_REMINDER", decided_by="AUTOMATION",
        )
    except Exception:
        logger.exception("Automatic reminder communication failed for case %s (non-fatal)", case.id)
        return SequenceDecision(False, "Reminder attempt failed unexpectedly.")

    return SequenceDecision(comm.status in ("SENT", "DELIVERED"), f"Reminder attempt result: {comm.status}", comm)
