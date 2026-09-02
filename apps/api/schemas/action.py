"""
RECON OS — Phase 3 (ACT) Action Schemas

Structured contracts for policy-gated recovery actions.

    Strategy  ->  Policy  ->  ActionProposal  ->  (Action Executor)  ->  Razorpay Adapter

Nothing here executes anything. The Action Executor re-loads the case and
RE-EVALUATES policy server-side before any Razorpay call — a frontend- or
AI-supplied "approved" value is never trusted.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------
class ActionType(str, Enum):
    # Phase 3 implements CREATE_PAYMENT_LINK only. The others are named for the
    # roadmap but are NOT executable yet.
    CREATE_PAYMENT_LINK = "CREATE_PAYMENT_LINK"


class ActionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"          # policy re-check passed, ready to execute
    BLOCKED = "BLOCKED"            # policy / config / eligibility blocked execution
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"          # provider action created (e.g. Payment Link)
    FAILED = "FAILED"             # provider call failed


class RecoveryOutcome(str, Enum):
    PENDING = "PENDING"           # action executed, awaiting real payment
    RECOVERED = "RECOVERED"       # Razorpay confirms payment_link.status == "paid", full amount
    PARTIAL = "PARTIAL"          # amount_paid < expected — NOT recovered, case NOT resolved
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class ActionBlockedReason(str, Enum):
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    POLICY_REJECTED = "POLICY_REJECTED"
    STRATEGY_NOT_ELIGIBLE = "STRATEGY_NOT_ELIGIBLE"
    CASE_NOT_ELIGIBLE = "CASE_NOT_ELIGIBLE"
    NOT_ANALYZED = "NOT_ANALYZED"
    RAZORPAY_NOT_CONFIGURED = "RAZORPAY_NOT_CONFIGURED"
    RAZORPAY_NOT_TEST_KEY = "RAZORPAY_NOT_TEST_KEY"
    TEST_MODE_DISABLED = "TEST_MODE_DISABLED"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_CURRENCY = "INVALID_CURRENCY"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    HUMAN_REJECTED = "HUMAN_REJECTED"


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------
class ActionProposal(BaseModel):
    """An instruction for the Action Engine to validate — NOT an execution."""
    proposable: bool
    action_type: Optional[ActionType] = None
    recovery_case_id: str
    case_number: str
    amount: Optional[Decimal] = None
    currency: str = "INR"
    reference_id: Optional[str] = None
    reason: str
    strategy_action: Optional[str] = None      # what the Strategy layer recommended
    policy_verdict: Optional[str] = None        # verdict at proposal time (display only)
    not_proposable_reason: Optional[str] = None
    test_mode: bool = True
    razorpay_configured: bool = False
    simulator_enabled: bool = False            # is the (non-real) simulator switched on?
    automatic_execution_enabled: bool = False  # see ActionResponse.automatic_execution_enabled


# ---------------------------------------------------------------------------
# Action record (API view)
# ---------------------------------------------------------------------------
class ActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recovery_case_id: str
    case_number: Optional[str] = None
    action_type: str
    status: str
    outcome: str
    ui_state: Optional[str] = None              # READY|APPROVED|EXECUTING|EXECUTED|WAITING_FOR_PAYMENT|RECOVERED|FAILED|BLOCKED|NEEDS_APPROVAL

    reference_id: Optional[str] = None
    provider: Optional[str] = None
    provider_action_id: Optional[str] = None    # e.g. plink_xxx
    provider_status: Optional[str] = None
    payment_link_url: Optional[str] = None      # public short_url — safe to expose

    amount: Optional[Decimal] = None
    currency: str = "INR"
    recovered_amount: Decimal = Decimal("0.00")
    simulated: bool = False                     # outcome set by the simulator, not a real payment
    simulator_enabled: bool = False
    # True only when RECON is CONFIGURED to auto-execute Policy-APPROVED
    # actions (see AUTOMATIC_ACTION_EXECUTION_ENABLED) — lets the frontend
    # honestly say "automatically executed" instead of implying a person
    # manually triggered it, without inventing a new DB field.
    automatic_execution_enabled: bool = False

    strategy_action: Optional[str] = None
    policy_verdict: Optional[str] = None
    blocked_reason: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    requested_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Human approval (Phase 4) — distinct from `approved_at` (automatic policy
    # approval). Present only once a human has actually recorded a decision.
    human_decision: Optional[str] = None        # APPROVED | REJECTED
    human_decided_at: Optional[datetime] = None
    human_decided_by: Optional[str] = None


class ActionListResponse(BaseModel):
    items: List[ActionResponse] = []
    total: int = 0


class ExecuteActionResponse(BaseModel):
    ok: bool
    message: str
    action: ActionResponse


class ReconcileActionResponse(BaseModel):
    ok: bool                                   # True only when the action is now RECOVERED
    recovered: bool
    partial: bool
    razorpay_status: Optional[str] = None      # authoritative payment_link.status from Razorpay
    amount_paid: Optional[Decimal] = None
    message: str
    action: ActionResponse


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class ActionMetrics(BaseModel):
    actions_proposed: int = 0
    actions_executed: int = 0
    actions_blocked: int = 0
    payment_links_created: int = 0
    pending_recoveries: int = 0
    partial_recoveries: int = 0
    unknown_outcomes: int = 0            # awaiting verification — never auto-retried
    revenue_recovered: Decimal = Decimal("0.00")       # REAL recoveries only
    simulated_revenue_recovered: Decimal = Decimal("0.00")
    recovery_rate: float = 0.0            # real recovered / executed
    test_mode: bool = True
    razorpay_configured: bool = False
    simulator_enabled: bool = False
