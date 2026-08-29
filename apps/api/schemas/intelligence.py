"""
RECON OS — Phase 2 (THINK) Intelligence Schemas

Structured, typed contracts for the deterministic intelligence pipeline:

    CaseContext -> Diagnosis -> RecoveryPrediction -> StrategyRecommendation -> PolicyEvaluation

All models are plain Pydantic (no ORM). Every field is explainable and every
component is deterministic. Nothing here calls an LLM or a payment API.
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
class FailureCategory(str, Enum):
    AUTH_TIMEOUT = "AUTH_TIMEOUT"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    BANK_DECLINE = "BANK_DECLINE"
    TECHNICAL_GATEWAY = "TECHNICAL_GATEWAY"
    RISK_BLOCK = "RISK_BLOCK"
    USER_ABANDONED = "USER_ABANDONED"
    UNKNOWN = "UNKNOWN"


class PredictionBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class StrategyAction(str, Enum):
    RETRY_NOW = "RETRY_NOW"
    RETRY_DELAYED = "RETRY_DELAYED"
    SEND_PAYMENT_LINK = "SEND_PAYMENT_LINK"
    CUSTOMER_OUTREACH = "CUSTOMER_OUTREACH"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_ACTION = "NO_ACTION"


class PolicyVerdict(str, Enum):
    APPROVED = "APPROVED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    REJECTED = "REJECTED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IntelligenceStatus(str, Enum):
    """Lifecycle stored on CaseIntelligence.status."""
    DETECTED = "DETECTED"
    DIAGNOSING = "DIAGNOSING"
    ANALYZED = "ANALYZED"
    POLICY_APPROVED = "POLICY_APPROVED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    POLICY_REJECTED = "POLICY_REJECTED"
    FAILED = "FAILED"


VERDICT_TO_STATUS = {
    PolicyVerdict.APPROVED.value: IntelligenceStatus.POLICY_APPROVED.value,
    PolicyVerdict.NEEDS_APPROVAL.value: IntelligenceStatus.NEEDS_APPROVAL.value,
    PolicyVerdict.REJECTED.value: IntelligenceStatus.POLICY_REJECTED.value,
}


# ---------------------------------------------------------------------------
# 1. Case Context
# ---------------------------------------------------------------------------
class CaseContext(BaseModel):
    """
    A deterministic, point-in-time snapshot of everything the intelligence
    pipeline is allowed to reason about. Built exclusively from real database
    rows — no invented behaviour, no random values.
    """
    model_config = ConfigDict(from_attributes=True)

    # Recovery case
    case_id: str
    case_number: str
    case_status: str
    amount: Decimal
    currency: str = "INR"
    attempt_count: int = 0
    max_attempts: int = 3
    opened_at: Optional[datetime] = None
    hours_since_failure: float = 0.0

    # Payment
    payment_id: Optional[str] = None
    payment_status: Optional[str] = None
    payment_method: Optional[str] = None
    failure_code: Optional[str] = None
    failure_reason: Optional[str] = None
    failure_description: Optional[str] = None

    # Customer
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_successful_payments: int = 0
    customer_failed_payments: int = 0
    customer_lifetime_amount: Decimal = Decimal("0.00")
    customer_success_rate: float = 0.0
    customer_has_history: bool = False

    # Prior recovery activity for this customer (excludes the current case)
    previous_recovery_cases: int = 0
    previous_resolved_cases: int = 0
    previous_recovery_attempts: int = 0

    # Contact governance (Phase 3 will populate; 0 for Phase 2)
    customer_contacts_last_24h: int = 0

    # Derived helper
    amount_band: str = "UNKNOWN"


# ---------------------------------------------------------------------------
# 2. Diagnosis
# ---------------------------------------------------------------------------
class DiagnosisResult(BaseModel):
    failure_category: FailureCategory
    probable_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence: List[str] = []
    provider: str = "DETERMINISTIC"


# ---------------------------------------------------------------------------
# 3. Recovery Prediction
# ---------------------------------------------------------------------------
class FeatureContribution(BaseModel):
    feature: str
    value: str
    contribution: float
    direction: str  # "positive" | "negative" | "neutral"
    note: Optional[str] = None


class PredictionResult(BaseModel):
    recovery_probability: float = Field(ge=0.0, le=1.0)
    band: PredictionBand
    confidence: float = Field(ge=0.0, le=1.0)
    base_rate: float
    features_used: List[FeatureContribution] = []
    rationale: str
    provider: str = "DETERMINISTIC"


# ---------------------------------------------------------------------------
# 4. Strategy Recommendation
# ---------------------------------------------------------------------------
class StrategyAlternative(BaseModel):
    action: StrategyAction
    reason: str


class StrategyResult(BaseModel):
    action: StrategyAction
    params: Dict[str, Any] = {}
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    alternatives: List[StrategyAlternative] = []
    provider: str = "DETERMINISTIC"


# ---------------------------------------------------------------------------
# 5. Policy Evaluation
# ---------------------------------------------------------------------------
class PolicyRuleResult(BaseModel):
    rule_id: str
    name: str
    description: str
    passed: bool
    detail: str


class PolicyResult(BaseModel):
    verdict: PolicyVerdict
    risk_level: RiskLevel
    requires_human: bool
    reason: str
    evaluated_rules: List[PolicyRuleResult] = []
    violated_rules: List[str] = []
    allowed_actions: List[StrategyAction] = []
    provider: str = "DETERMINISTIC"


# ---------------------------------------------------------------------------
# Composite result + API envelopes
# ---------------------------------------------------------------------------
class IntelligenceResult(BaseModel):
    case_id: str
    case_number: str
    status: str
    provider: str
    version: str
    diagnosis: DiagnosisResult
    prediction: PredictionResult
    strategy: StrategyResult
    policy: PolicyResult
    context: CaseContext


class IntelligenceEnvelope(BaseModel):
    """Response shape for the intelligence API endpoints."""
    case_id: str
    case_number: str
    analyzed: bool
    intelligence_enabled: bool
    status: str
    provider: Optional[str] = None
    version: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    diagnosis: Optional[Dict[str, Any]] = None
    prediction: Optional[Dict[str, Any]] = None
    strategy: Optional[Dict[str, Any]] = None
    policy: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class IntelligenceSummary(BaseModel):
    """Compact intelligence view attached to recovery case responses."""
    status: str
    provider: str
    version: str
    failure_category: Optional[str] = None
    recovery_probability: Optional[float] = None
    prediction_band: Optional[str] = None
    recommended_action: Optional[str] = None
    policy_verdict: Optional[str] = None
    requires_human: Optional[bool] = None
    risk_level: Optional[str] = None
    analyzed_at: Optional[datetime] = None


class IntelligenceListItem(BaseModel):
    case_id: str
    case_number: str
    customer_name: Optional[str] = None
    amount_at_risk: Decimal
    currency: str = "INR"
    failure_category: Optional[str] = None
    recovery_probability: Optional[float] = None
    prediction_band: Optional[str] = None
    recommended_action: Optional[str] = None
    policy_verdict: Optional[str] = None
    risk_level: Optional[str] = None
    status: str
    provider: str
    version: str
    analyzed_at: Optional[datetime] = None


class IntelligenceListResponse(BaseModel):
    items: List[IntelligenceListItem]
    total: int
    page: int
    limit: int


class IntelligenceMetrics(BaseModel):
    cases_analyzed: int = 0
    high_recovery_probability: int = 0
    needs_approval: int = 0
    policy_rejected: int = 0
    policy_approved: int = 0
