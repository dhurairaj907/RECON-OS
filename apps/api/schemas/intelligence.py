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

    # --- Phase 10: intent-aware recovery signals (additive, all defaulted) ---
    # Payment links this customer was sent, across any of their cases, that
    # they let expire or that were cancelled without paying — a real,
    # already-stored signal (RecoveryAction.outcome), not a new tracking
    # mechanism.
    customer_expired_or_cancelled_links: int = 0
    # Customer has explicitly opted out of at least one communication
    # channel (Customer.opted_out_channels) — an unambiguous "do not
    # contact" signal already captured elsewhere in the system.
    customer_opted_out: bool = False
    # Payment.refunded_amount_paise / dispute_status (Phase 9) aggregated
    # across this customer's OTHER payments.
    customer_refunded_payment_count: int = 0
    customer_disputed_payment_count: int = 0
    # Prior cases for this customer whose diagnosis was USER_ABANDONED.
    customer_prior_user_abandoned_count: int = 0

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
    provider: str = "DETERMINISTIC"          # "DETERMINISTIC" | "GEMINI" | "NVIDIA_NIM"
    provider_version: Optional[str] = None   # e.g. "gemini-2.0-flash" / "deterministic-2.5"
    fallback_reason: Optional[str] = None    # set when an AI attempt fell back to deterministic


class AIDiagnosisSchema(BaseModel):
    """
    The STRICT shape requested from and validated for an LLM diagnosis response.
    Deliberately minimal: an LLM can only return these fields — it has no field
    through which to authorise an action or influence policy.
    """
    model_config = ConfigDict(extra="ignore")

    failure_category: FailureCategory
    probable_cause: str = Field(min_length=1, max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=800)
    evidence: List[str] = Field(default_factory=list, max_length=12)


# ---------------------------------------------------------------------------
# 2.5 Intent Evaluation  (Phase 10)
# ---------------------------------------------------------------------------
class IntentClassification(str, Enum):
    RECOVERABLE = "RECOVERABLE"
    AMBIGUOUS = "AMBIGUOUS"
    LIKELY_UNWILLING = "LIKELY_UNWILLING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class IntentSignal(BaseModel):
    code: str
    description: str


class IntentResult(BaseModel):
    """
    Distinct from DiagnosisResult (why did it fail?) and PredictionResult
    (how likely is recovery to work?) — this answers "does RECON have reason
    to believe the customer WANTS to be recovered?". Feeds the Policy Engine
    as additional structured evidence; never bypasses it (see
    policy_engine.py RULE_INTENT_UNWILLING / RULE_INTENT_EVIDENCE).
    """
    classification: IntentClassification
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: List[str] = []
    positive_signals: List[IntentSignal] = []
    negative_signals: List[IntentSignal] = []
    # Signals the directive asked for that the current data model cannot
    # supply (no click tracking, no inbound customer replies, no mandate/
    # subscription model) — reported honestly, never fabricated.
    unavailable_signals: List[str] = []
    evidence_completeness: float = Field(ge=0.0, le=1.0)
    rationale: str
    provider: str = "DETERMINISTIC"          # "DETERMINISTIC" | "GEMINI" | "NVIDIA_NIM"
    provider_version: Optional[str] = None
    evaluated_at: datetime


class AIIntentSchema(BaseModel):
    """
    The STRICT shape requested from and validated for an LLM intent opinion —
    mirrors AIDiagnosisSchema exactly. An LLM can only return these fields;
    it has no field through which to authorise an action, change a signal
    value, or influence anything outside this classification.
    """
    model_config = ConfigDict(extra="ignore")

    classification: IntentClassification
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: List[str] = Field(default_factory=list, max_length=12)
    rationale: str = Field(min_length=1, max_length=800)


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
    provider: Optional[str] = None            # "DETERMINISTIC" | "GEMINI" | "NVIDIA_NIM"
    provider_version: Optional[str] = None
    intelligence_version: Optional[str] = None
    diagnosis_source: Optional[str] = None    # "AI-ENHANCED" | "DETERMINISTIC FALLBACK" | "DETERMINISTIC"
    version: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    diagnosis: Optional[Dict[str, Any]] = None
    prediction: Optional[Dict[str, Any]] = None
    strategy: Optional[Dict[str, Any]] = None
    intent: Optional[Dict[str, Any]] = None
    policy: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class IntentEnvelope(BaseModel):
    """Response shape for GET /api/v1/recovery-cases/{case_id}/intent."""
    case_id: str
    case_number: str
    evaluated: bool
    intent: Optional[IntentResult] = None


class IntelligenceSummary(BaseModel):
    """Compact intelligence view attached to recovery case responses."""
    status: str
    provider: str
    provider_version: Optional[str] = None
    intelligence_version: Optional[str] = None
    diagnosis_source: Optional[str] = None
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
    provider_version: Optional[str] = None
    diagnosis_source: Optional[str] = None
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
    ai_enhanced: int = 0          # latest analyses whose diagnosis came from an LLM
    deterministic: int = 0        # latest analyses using the deterministic engine
    ai_configured: bool = False   # LLM_ENABLED + a provider selected (server-side)
