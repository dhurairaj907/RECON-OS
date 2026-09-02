"""
RECON OS — Phase 4 (PROVE): Revenue Recovery Analytics Schemas

Every field here is computed from real persisted rows (RecoveryCase,
RecoveryAction, CaseIntelligence) — see services/analytics_service.py. A
metric that cannot be honestly computed from current data is left `None`
rather than fabricated; the frontend must render that as "not yet available",
never as zero.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class StrategyPerformance(BaseModel):
    strategy: str
    executed: int
    recovered: int
    success_rate: float


class ChannelPerformance(BaseModel):
    channel: str
    attempted: int
    sent: int
    delivered: int
    failed: int


class CommunicationAnalytics(BaseModel):
    """
    Phase 7: communication funnel metrics computed directly from persisted
    Communication rows — never fabricated, never confusing "a message was
    sent" with "revenue was recovered". `cases_with_communication` /
    `cases_with_communication_recovered` are a real, computed CORRELATION
    (cases that received at least one SENT/DELIVERED message before/at
    recovery) — explicitly not a causal claim.
    """
    messages_attempted: int = 0
    messages_sent: int = 0
    messages_delivered: int = 0
    messages_failed: int = 0
    channel_performance: List[ChannelPerformance] = []

    cases_with_communication: int = 0
    cases_with_communication_recovered: int = 0
    communication_to_recovery_rate: Optional[float] = None
    recovery_value_from_communicated_cases: Decimal = Decimal("0.00")


class AnalyticsMetrics(BaseModel):
    generated_at: datetime

    # --- Revenue ---
    revenue_at_risk: Decimal
    # Revenue at risk MINUS cases whose most recent action is a hard policy
    # rejection (a genuine dead end under current policy) — a real, computed
    # distinction from raw revenue_at_risk, not a duplicate of it.
    potential_recoverable_revenue: Decimal
    # Phase 9: net of any later refund on the fulfilling payment — "REAL
    # RECOVERED REVENUE" means revenue actually confirmed AND still held.
    # See services/analytics_service.py::compute_analytics.
    revenue_recovered: Decimal
    # Phase 9: the portion of gross recovered revenue later refunded —
    # exposed separately so revenue_recovered's net figure is never
    # confused with "nothing was ever refunded".
    revenue_refunded: Decimal = Decimal("0.00")
    # Phase 9: count of RECONCILIATION_MISMATCH / PAYMENT_STATE_RECONCILIATION_MISMATCH
    # audit rows for this organization — see GET /api/v1/reconciliation/mismatches
    # for the full list.
    reconciliation_mismatches_total: int = 0
    simulated_revenue_recovered: Decimal
    recovery_rate: float
    average_recovery_probability: Optional[float] = None

    # --- Automation vs human intervention ---
    automation_rate: Optional[float] = None          # of EXECUTED actions, fraction with no human decision
    human_approval_rate: Optional[float] = None       # of actions with a human decision, fraction APPROVED
    human_rejection_rate: Optional[float] = None      # of actions with a human decision, fraction REJECTED
    actions_needing_approval_total: int = 0
    actions_approved_by_human: int = 0
    actions_rejected_by_human: int = 0

    # --- Failure / safety ---
    recovery_failure_rate: Optional[float] = None     # of attempted executions, fraction definitively FAILED
    unknown_cases: int = 0
    policy_rejection_count: int = 0

    # --- Operational ---
    average_recovery_time_hours: Optional[float] = None   # RECOVERED actions only (requested_at -> completed_at)
    average_recovery_attempts: float = 0.0
    total_recovery_attempts: int = 0

    strategy_performance: List[StrategyPerformance] = []

    # --- Coverage metadata (so the UI can label small-sample metrics honestly) ---
    cases_analyzed: int = 0
    actions_total: int = 0

    # --- Phase 7: communications ---
    communications: CommunicationAnalytics = CommunicationAnalytics()
