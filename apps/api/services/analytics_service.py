"""
RECON OS — Phase 4 (PROVE): Revenue Recovery Analytics

Computes business/operational metrics directly from persisted RecoveryCase,
RecoveryAction and CaseIntelligence rows — the exact same tables the
dashboard, recovery, intelligence and audit views already read. No new
tracking tables, no fabricated numbers: a metric with no honest basis in
current data is returned as `None`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.case_intelligence import CaseIntelligence
from models.communication import Communication
from models.payment import Payment
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from schemas.analytics import AnalyticsMetrics, ChannelPerformance, CommunicationAnalytics, StrategyPerformance

# Both mismatch audit action names feed reconciliation_mismatches_total —
# the case-level "already RESOLVED" check (event_processor.py §6b) and the
# general payment-lifecycle checker (services/reconciliation.py) are two
# detectors writing into the same honest count, never two separate metrics
# for what a user experiences as one thing: "a mismatch was found".
_MISMATCH_AUDIT_ACTIONS = ("RECONCILIATION_MISMATCH", "PAYMENT_STATE_RECONCILIATION_MISMATCH")

_ACTIVE_CASE_STATUSES = ("DETECTED", "OPEN")


def _latest_action_per_case(actions: list[RecoveryAction]) -> dict:
    latest: dict = {}
    for a in actions:
        cur = latest.get(a.recovery_case_id)
        if cur is None or (a.created_at or datetime.min) > (cur.created_at or datetime.min):
            latest[a.recovery_case_id] = a
    return latest


def compute_analytics(db: Session, merchant_id: UUID) -> AnalyticsMetrics:
    cases = db.query(RecoveryCase).filter(RecoveryCase.merchant_id == merchant_id).all()
    actions = db.query(RecoveryAction).filter(RecoveryAction.merchant_id == merchant_id).all()
    intel_rows = (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.merchant_id == merchant_id)
        .order_by(CaseIntelligence.recovery_case_id, desc(CaseIntelligence.version))
        .all()
    )
    latest_intel: dict = {}
    for r in intel_rows:
        latest_intel.setdefault(r.recovery_case_id, r)

    # --- Revenue ---
    active_cases = [c for c in cases if (c.status or "") in _ACTIVE_CASE_STATUSES]
    revenue_at_risk = sum((Decimal(c.amount_at_risk or 0) for c in active_cases), Decimal("0.00"))

    latest_action_by_case = _latest_action_per_case(actions)
    dead_end_case_ids = {
        case_id for case_id, a in latest_action_by_case.items()
        if (a.blocked_reason or "") == "POLICY_REJECTED"
    }
    potential_recoverable_revenue = sum(
        (Decimal(c.amount_at_risk or 0) for c in active_cases if c.id not in dead_end_case_ids),
        Decimal("0.00"),
    )

    recovered = [a for a in actions if (a.outcome or "") == "RECOVERED"]
    real_recovered = [a for a in recovered if not a.simulated]
    sim_recovered = [a for a in recovered if a.simulated]
    simulated_revenue_recovered = sum((Decimal(a.recovered_amount or 0) for a in sim_recovered), Decimal("0.00"))

    # --- Phase 9: net revenue_recovered of any later refund ---------------
    # "REAL RECOVERED REVENUE" means revenue actually confirmed AND still
    # held — a fully refunded payment-link recovery is not permanently
    # recovered revenue, even though RecoveryAction.outcome correctly stays
    # RECOVERED (recovery lifecycle is never rewritten by a later refund;
    # see services/reconciliation.py).
    fulfilling_ids = {a.fulfilling_payment_id for a in real_recovered if a.fulfilling_payment_id}
    refunded_paise_by_payment: dict = {}
    if fulfilling_ids:
        for p in db.query(Payment).filter(Payment.id.in_(fulfilling_ids)).all():
            refunded_paise_by_payment[p.id] = int(p.refunded_amount_paise or 0)

    revenue_recovered = Decimal("0.00")
    revenue_refunded = Decimal("0.00")
    for a in real_recovered:
        amt = Decimal(a.recovered_amount or 0)
        refunded = Decimal(refunded_paise_by_payment.get(a.fulfilling_payment_id, 0)) / Decimal("100")
        refunded = min(refunded, amt)  # never subtract more than was ever recovered on this action
        revenue_recovered += (amt - refunded)
        revenue_refunded += refunded

    executed = [a for a in actions if a.status == "EXECUTED"]
    recovery_rate = (len(real_recovered) / len(executed)) if executed else 0.0

    probabilities = [
        float(r.recovery_probability) for r in latest_intel.values()
        if r.recovery_probability is not None
    ]
    average_recovery_probability = (
        round(sum(probabilities) / len(probabilities), 4) if probabilities else None
    )

    # --- Automation vs human intervention ---
    automation_rate = (
        round(sum(1 for a in executed if not a.human_decision) / len(executed), 4)
        if executed else None
    )
    decided = [a for a in actions if a.human_decision]
    actions_approved_by_human = sum(1 for a in decided if a.human_decision == "APPROVED")
    actions_rejected_by_human = sum(1 for a in decided if a.human_decision == "REJECTED")
    human_approval_rate = round(actions_approved_by_human / len(decided), 4) if decided else None
    human_rejection_rate = round(actions_rejected_by_human / len(decided), 4) if decided else None
    actions_needing_approval_total = sum(
        1 for a in actions if (a.blocked_reason or "") == "NEEDS_APPROVAL" or a.human_decision
    )

    # --- Failure / safety ---
    attempted = [a for a in actions if a.status in ("EXECUTED", "FAILED")]
    recovery_failure_rate = (
        round(sum(1 for a in attempted if a.status == "FAILED") / len(attempted), 4)
        if attempted else None
    )
    unknown_cases = sum(1 for a in actions if (a.outcome or "") == "UNKNOWN")
    policy_rejection_count = sum(1 for a in actions if (a.blocked_reason or "") == "POLICY_REJECTED")

    # --- Operational ---
    recovery_durations = [
        (a.completed_at - a.requested_at).total_seconds() / 3600.0
        for a in real_recovered
        if a.completed_at is not None and a.requested_at is not None
    ]
    average_recovery_time_hours = (
        round(sum(recovery_durations) / len(recovery_durations), 2) if recovery_durations else None
    )
    total_recovery_attempts = sum(int(c.attempt_count or 0) for c in cases)
    average_recovery_attempts = round(total_recovery_attempts / len(cases), 2) if cases else 0.0

    by_strategy: dict = defaultdict(lambda: {"executed": 0, "recovered": 0})
    for a in actions:
        if not a.strategy_action or a.status != "EXECUTED":
            continue
        by_strategy[a.strategy_action]["executed"] += 1
        if (a.outcome or "") == "RECOVERED" and not a.simulated:
            by_strategy[a.strategy_action]["recovered"] += 1
    strategy_performance = [
        StrategyPerformance(
            strategy=name,
            executed=v["executed"],
            recovered=v["recovered"],
            success_rate=round(v["recovered"] / v["executed"], 4) if v["executed"] else 0.0,
        )
        for name, v in sorted(by_strategy.items())
    ]

    # --- Phase 7: communications ---
    comms = db.query(Communication).filter(Communication.merchant_id == merchant_id).all()
    by_channel: dict = defaultdict(lambda: {"attempted": 0, "sent": 0, "delivered": 0, "failed": 0})
    messages_sent = messages_delivered = messages_failed = 0
    for c in comms:
        by_channel[c.channel]["attempted"] += 1
        if c.status == "SENT":
            messages_sent += 1
            by_channel[c.channel]["sent"] += 1
        elif c.status == "DELIVERED":
            messages_sent += 1
            messages_delivered += 1
            by_channel[c.channel]["sent"] += 1
            by_channel[c.channel]["delivered"] += 1
        elif c.status == "FAILED":
            messages_failed += 1
            by_channel[c.channel]["failed"] += 1
    channel_performance = [
        ChannelPerformance(channel=name, **v) for name, v in sorted(by_channel.items())
    ]

    communicated_case_ids = {
        c.recovery_case_id for c in comms if c.status in ("SENT", "DELIVERED")
    }
    cases_with_communication = len(communicated_case_ids)
    recovered_case_ids = {a.recovery_case_id for a in real_recovered}
    cases_with_communication_recovered = len(communicated_case_ids & recovered_case_ids)
    communication_to_recovery_rate = (
        round(cases_with_communication_recovered / cases_with_communication, 4)
        if cases_with_communication else None
    )
    recovery_value_from_communicated_cases = sum(
        (Decimal(a.recovered_amount or 0) for a in real_recovered if a.recovery_case_id in communicated_case_ids),
        Decimal("0.00"),
    )
    communications_analytics = CommunicationAnalytics(
        messages_attempted=len(comms),
        messages_sent=messages_sent,
        messages_delivered=messages_delivered,
        messages_failed=messages_failed,
        channel_performance=channel_performance,
        cases_with_communication=cases_with_communication,
        cases_with_communication_recovered=cases_with_communication_recovered,
        communication_to_recovery_rate=communication_to_recovery_rate,
        recovery_value_from_communicated_cases=recovery_value_from_communicated_cases,
    )

    reconciliation_mismatches_total = (
        db.query(AuditLog)
        .filter(AuditLog.merchant_id == merchant_id, AuditLog.action.in_(_MISMATCH_AUDIT_ACTIONS))
        .count()
    )

    return AnalyticsMetrics(
        generated_at=datetime.now(timezone.utc),
        revenue_at_risk=revenue_at_risk,
        potential_recoverable_revenue=potential_recoverable_revenue,
        revenue_recovered=revenue_recovered,
        revenue_refunded=revenue_refunded,
        reconciliation_mismatches_total=reconciliation_mismatches_total,
        simulated_revenue_recovered=simulated_revenue_recovered,
        recovery_rate=round(recovery_rate, 4),
        average_recovery_probability=average_recovery_probability,
        automation_rate=automation_rate,
        human_approval_rate=human_approval_rate,
        human_rejection_rate=human_rejection_rate,
        actions_needing_approval_total=actions_needing_approval_total,
        actions_approved_by_human=actions_approved_by_human,
        actions_rejected_by_human=actions_rejected_by_human,
        recovery_failure_rate=recovery_failure_rate,
        unknown_cases=unknown_cases,
        policy_rejection_count=policy_rejection_count,
        average_recovery_time_hours=average_recovery_time_hours,
        average_recovery_attempts=average_recovery_attempts,
        total_recovery_attempts=total_recovery_attempts,
        strategy_performance=strategy_performance,
        cases_analyzed=len(latest_intel),
        actions_total=len(actions),
        communications=communications_analytics,
    )
