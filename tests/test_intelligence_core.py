"""
RECON OS — Phase 2 (THINK) Intelligence Core Tests

Covers the deterministic pipeline components in isolation:
Context Builder, Diagnosis, Prediction, Strategy, Policy Engine.
"""

from decimal import Decimal

import pytest

from config import settings
from models.merchant import Merchant
from schemas.intelligence import (
    CaseContext,
    FailureCategory,
    PolicyVerdict,
    PredictionBand,
    StrategyAction,
)
from services.event_processor import process_inbound_event
from services.intelligence.context_builder import build_case_context
from services.intelligence.diagnosis import diagnose
from services.intelligence.policy_engine import evaluate_policy
from services.intelligence.prediction import predict
from services.intelligence.strategy import recommend_strategy
from services.intelligence.weights import amount_band
from models.recovery_case import RecoveryCase


def make_context(**overrides) -> CaseContext:
    base = dict(
        case_id="00000000-0000-0000-0000-000000000000",
        case_number="RC-TEST",
        case_status="DETECTED",
        amount=Decimal("4999.00"),
        currency="INR",
        attempt_count=0,
        max_attempts=3,
        hours_since_failure=0.5,
        payment_id="pay_test",
        payment_status="failed",
        payment_method="upi",
        failure_code="BAD_REQUEST_ERROR",
        failure_reason="payment_failed",
        failure_description="UPI handle authorization timeout on customer app",
        customer_successful_payments=0,
        customer_failed_payments=1,
        customer_lifetime_amount=Decimal("0.00"),
        customer_success_rate=0.0,
        customer_has_history=False,
        previous_recovery_cases=0,
        previous_resolved_cases=0,
        previous_recovery_attempts=0,
        customer_contacts_last_24h=0,
    )
    base.update(overrides)
    base["amount_band"] = amount_band(Decimal(base["amount"]))
    return CaseContext(**base)


def full_pipeline(ctx: CaseContext):
    d = diagnose(ctx)
    p = predict(ctx, d)
    s = recommend_strategy(ctx, d, p)
    pol = evaluate_policy(ctx, d, p, s)
    return d, p, s, pol


# ---------------------------------------------------------------------------
# 1. Context Builder
# ---------------------------------------------------------------------------
def test_context_builder_reads_real_data(db_session, sample_payment_failed_payload):
    merchant = db_session.query(Merchant).first()
    _, case = process_inbound_event(
        db=db_session,
        raw_payload=sample_payment_failed_payload,
        merchant_id=merchant.id,
    )
    ctx = build_case_context(db_session, case)

    assert ctx.case_number == case.case_number
    assert ctx.amount == Decimal("8499.00")
    assert ctx.currency == "INR"
    assert ctx.payment_method == "upi"
    assert ctx.payment_status == "failed"
    assert ctx.failure_code == "BAD_REQUEST_ERROR"
    assert ctx.customer_failed_payments == 1
    assert ctx.customer_successful_payments == 0
    assert ctx.attempt_count == 0
    assert ctx.max_attempts == 3
    assert ctx.amount_band == "SMALL"
    assert ctx.hours_since_failure >= 0.0
    # no invented history
    assert ctx.previous_recovery_cases == 0


def test_context_builder_has_no_side_effects(db_session, sample_payment_failed_payload):
    merchant = db_session.query(Merchant).first()
    _, case = process_inbound_event(
        db=db_session,
        raw_payload=sample_payment_failed_payload,
        merchant_id=merchant.id,
    )
    before = db_session.query(RecoveryCase).count()
    build_case_context(db_session, case)
    build_case_context(db_session, case)
    assert db_session.query(RecoveryCase).count() == before


# ---------------------------------------------------------------------------
# 2 & 3. Diagnosis
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "desc,reason,method,expected",
    [
        ("UPI handle authorization timeout on customer app", "payment_failed", "upi",
         FailureCategory.AUTH_TIMEOUT),
        ("Transaction declined: Insufficient funds / limit exceeded", "payment_failed", "card",
         FailureCategory.INSUFFICIENT_FUNDS),
        ("Payment declined by issuing bank - do not honour", "payment_failed", "card",
         FailureCategory.BANK_DECLINE),
        ("Payment blocked by risk engine - suspected fraudulent transaction",
         "payment_risk_check_failed", "card", FailureCategory.RISK_BLOCK),
        ("Gateway timeout - downstream processor unavailable", "payment_failed", "netbanking",
         FailureCategory.AUTH_TIMEOUT),  # 'timeout' keyword wins (priority order)
        ("Customer cancelled by user before completing payment", "payment_failed", "upi",
         FailureCategory.USER_ABANDONED),
        ("", None, "card", FailureCategory.UNKNOWN),
    ],
)
def test_diagnosis_categories(desc, reason, method, expected):
    ctx = make_context(failure_description=desc, failure_reason=reason, payment_method=method,
                       failure_code="")
    d = diagnose(ctx)
    assert d.failure_category == expected
    assert d.rationale
    assert d.evidence


def test_diagnosis_confidence_bounds():
    for desc in ["", "totally unrecognisable gibberish xyz", "insufficient funds timeout fraud declined"]:
        d = diagnose(make_context(failure_description=desc, failure_code="", failure_reason=None))
        assert 0.0 <= d.confidence <= 1.0


def test_diagnosis_gateway_error_code_fallback():
    d = diagnose(make_context(failure_description="", failure_reason=None, failure_code="GATEWAY_ERROR"))
    assert d.failure_category == FailureCategory.TECHNICAL_GATEWAY


# ---------------------------------------------------------------------------
# 4, 5, 6. Prediction
# ---------------------------------------------------------------------------
def test_prediction_is_deterministic():
    ctx = make_context(customer_successful_payments=9, customer_failed_payments=1,
                       customer_success_rate=0.9, customer_has_history=True)
    d = diagnose(ctx)
    p1 = predict(ctx, d)
    p2 = predict(ctx, d)
    assert p1.model_dump() == p2.model_dump()
    assert p1.recovery_probability == p2.recovery_probability


def test_prediction_bounds_and_band():
    for amount in [Decimal("100"), Decimal("4999"), Decimal("14999"), Decimal("75000"), Decimal("5000000")]:
        for attempts in [0, 1, 2, 3, 5]:
            ctx = make_context(amount=amount, attempt_count=attempts)
            d = diagnose(ctx)
            p = predict(ctx, d)
            assert 0.0 <= p.recovery_probability <= 1.0
            assert 0.0 <= p.confidence <= 1.0
            assert p.band in (PredictionBand.LOW, PredictionBand.MEDIUM, PredictionBand.HIGH)


def test_prediction_explains_contributions():
    ctx = make_context()
    d = diagnose(ctx)
    p = predict(ctx, d)
    features = {f.feature for f in p.features_used}
    assert "failure_category_base_rate" in features
    assert "attempt_count" in features
    assert "amount_band" in features
    assert p.rationale


def test_prediction_strong_history_raises_probability():
    weak = make_context(customer_successful_payments=1, customer_failed_payments=9,
                        customer_success_rate=0.1, customer_has_history=True)
    strong = make_context(customer_successful_payments=9, customer_failed_payments=1,
                          customer_success_rate=0.9, customer_has_history=True)
    dw, ds = diagnose(weak), diagnose(strong)
    assert predict(strong, ds).recovery_probability > predict(weak, dw).recovery_probability


# ---------------------------------------------------------------------------
# 7. Strategy
# ---------------------------------------------------------------------------
def test_strategy_technical_high_first_attempt_is_retry_now():
    ctx = make_context()
    d, p, s, _ = full_pipeline(ctx)
    assert d.failure_category == FailureCategory.AUTH_TIMEOUT
    assert p.band == PredictionBand.HIGH
    assert s.action == StrategyAction.RETRY_NOW
    assert s.alternatives


def test_strategy_risk_block_never_auto_retries():
    ctx = make_context(failure_description="blocked by risk engine fraud",
                       failure_reason="payment_risk_check_failed")
    d, p, s, _ = full_pipeline(ctx)
    assert d.failure_category == FailureCategory.RISK_BLOCK
    assert s.action == StrategyAction.MANUAL_REVIEW


def test_strategy_attempts_exhausted_is_no_action():
    ctx = make_context(attempt_count=3)
    _, _, s, _ = full_pipeline(ctx)
    assert s.action == StrategyAction.NO_ACTION


# ---------------------------------------------------------------------------
# 8-13. Policy Engine
# ---------------------------------------------------------------------------
def test_policy_approves_small_amount_technical_failure():
    ctx = make_context(amount=Decimal("4999.00"))
    _, _, _, pol = full_pipeline(ctx)
    assert pol.verdict == PolicyVerdict.APPROVED
    assert pol.requires_human is False
    assert pol.risk_level.value == "LOW"
    assert all(r.passed for r in pol.evaluated_rules)


def test_policy_amount_threshold_boundary():
    at_limit = make_context(amount=Decimal("5000.00"))
    over_limit = make_context(amount=Decimal("5000.01"))
    assert full_pipeline(at_limit)[3].verdict == PolicyVerdict.APPROVED
    assert full_pipeline(over_limit)[3].verdict == PolicyVerdict.NEEDS_APPROVAL


def test_policy_needs_approval_over_5000():
    ctx = make_context(amount=Decimal("14999.00"),
                       failure_description="Transaction declined: Insufficient funds",
                       payment_method="card")
    d, _, _, pol = full_pipeline(ctx)
    assert d.failure_category == FailureCategory.INSUFFICIENT_FUNDS
    assert pol.verdict == PolicyVerdict.NEEDS_APPROVAL
    assert pol.requires_human is True
    assert "RULE_HIGH_VALUE_APPROVAL" in pol.violated_rules


def test_policy_high_value_corporate_needs_approval_high_risk():
    ctx = make_context(amount=Decimal("75000.00"), payment_method="netbanking",
                       failure_description="Corporate netbanking approval limit exceeded")
    _, _, _, pol = full_pipeline(ctx)
    assert pol.verdict == PolicyVerdict.NEEDS_APPROVAL
    assert pol.risk_level.value == "HIGH"


def test_policy_rejects_fraud_for_automatic_retry():
    ctx = make_context(failure_description="Payment blocked by risk engine - fraud suspected",
                       failure_reason="payment_risk_check_failed")
    d, p, s, pol = full_pipeline(ctx)
    assert d.failure_category == FailureCategory.RISK_BLOCK
    assert pol.verdict == PolicyVerdict.REJECTED
    assert "RULE_FRAUD_NO_AUTO_RETRY" in pol.violated_rules
    assert StrategyAction.RETRY_NOW not in pol.allowed_actions
    assert StrategyAction.RETRY_DELAYED not in pol.allowed_actions


def test_policy_rejects_when_max_attempts_reached():
    ctx = make_context(attempt_count=3)
    _, _, _, pol = full_pipeline(ctx)
    assert pol.verdict == PolicyVerdict.REJECTED
    assert "RULE_MAX_ATTEMPTS" in pol.violated_rules


def test_policy_rejects_unknown_payment_state():
    ctx = make_context(payment_status="")
    _, _, _, pol = full_pipeline(ctx)
    assert pol.verdict == PolicyVerdict.REJECTED
    assert "RULE_PAYMENT_STATE_VERIFIED" in pol.violated_rules


def test_policy_all_rules_visible_in_output():
    ctx = make_context()
    _, _, _, pol = full_pipeline(ctx)
    rule_ids = {r.rule_id for r in pol.evaluated_rules}
    assert {
        "RULE_MAX_ATTEMPTS", "RULE_CONTACT_LIMIT", "RULE_AUTO_APPROVAL_AMOUNT",
        "RULE_HIGH_VALUE_APPROVAL", "RULE_FRAUD_NO_AUTO_RETRY",
        "RULE_PAYMENT_STATE_VERIFIED", "RULE_ALLOWED_STRATEGY",
    }.issubset(rule_ids)


def test_policy_constants_are_configurable(monkeypatch):
    monkeypatch.setattr(settings, "POLICY_AUTO_APPROVAL_AMOUNT_LIMIT", 20000.0)
    ctx = make_context(amount=Decimal("14999.00"),
                       failure_description="Transaction declined: Insufficient funds",
                       payment_method="card")
    _, _, _, pol = full_pipeline(ctx)
    # With a higher ceiling, 14,999 is now auto-approvable
    assert pol.verdict == PolicyVerdict.APPROVED
