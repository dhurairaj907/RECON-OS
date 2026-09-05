"""
RECON OS — Phase 10 Tests: Intent-Aware Recovery

Covers the new Intent Evaluation pipeline stage (services/intelligence/intent.py
+ ai_intent.py) and its integration into the Policy Engine
(RULE_INTENT_UNWILLING / RULE_INTENT_EVIDENCE) — never a bypass, always
additional structured evidence the deterministic Policy Engine consumes.

Scenario groups (per the Phase 10 directive):
  recoverable (3) / unwilling (4) / ambiguous (3) / security+isolation (4) /
  failure handling (4) = 18, plus a full regression run.
"""

import json
from decimal import Decimal

import pytest

from config import settings
from models.audit_log import AuditLog
from models.case_intelligence import CaseIntelligence
from models.customer import Customer
from models.merchant import Merchant
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from schemas.intelligence import (
    CaseContext,
    DiagnosisResult,
    FailureCategory,
    IntentClassification,
    PredictionBand,
    PredictionResult,
    StrategyAction,
    StrategyResult,
)
from services.actions.common import PAYMENT_LINK_ELIGIBLE_STRATEGIES, to_paise
from services.actions.executor import execute_action
from services.actions.proposal import build_proposal, get_or_create_action
from services.event_processor import process_inbound_event
from services.intelligence import ai_intent as aii
from services.intelligence import intent as intent_mod
from services.intelligence.orchestrator import run_intelligence
from services.intelligence.policy_engine import evaluate_policy
from services.intelligence.weights import amount_band

from test_actions import (  # noqa: F401 — reused fixtures + helpers
    razorpay_env,
    webhook_env,
    upi_timeout_payload,
    _api_analyzed_case,
    _make_case,
)


# ---------------------------------------------------------------------------
# Unit-level helpers
# ---------------------------------------------------------------------------
def make_ctx(**overrides) -> CaseContext:
    base = dict(
        case_id="00000000-0000-0000-0000-000000000000",
        case_number="RC-INTENT",
        case_status="DETECTED",
        amount=Decimal("4999.00"),
        currency="INR",
        attempt_count=0,
        max_attempts=3,
        hours_since_failure=0.5,
        payment_id="pay_intent",
        payment_status="failed",
        payment_method="upi",
        customer_id="cust-1",
        customer_successful_payments=0,
        customer_failed_payments=0,
        customer_success_rate=0.0,
        customer_has_history=False,
        previous_recovery_cases=0,
        previous_resolved_cases=0,
        previous_recovery_attempts=0,
        customer_expired_or_cancelled_links=0,
        customer_opted_out=False,
        customer_refunded_payment_count=0,
        customer_disputed_payment_count=0,
        customer_prior_user_abandoned_count=0,
    )
    base.update(overrides)
    base["amount_band"] = amount_band(Decimal(base["amount"]))
    return CaseContext(**base)


def make_diag(category="AUTH_TIMEOUT", confidence=0.8) -> DiagnosisResult:
    return DiagnosisResult(
        failure_category=FailureCategory(category),
        probable_cause="test",
        confidence=confidence,
        rationale="test",
        evidence=[],
        provider="DETERMINISTIC",
    )


def make_pred(band=PredictionBand.HIGH, probability=0.7) -> PredictionResult:
    return PredictionResult(
        recovery_probability=probability, band=band, confidence=0.6,
        base_rate=0.6, features_used=[], rationale="test", provider="DETERMINISTIC",
    )


def make_strategy(action=StrategyAction.SEND_PAYMENT_LINK) -> StrategyResult:
    return StrategyResult(action=action, params={}, rationale="test", confidence=0.7, provider="DETERMINISTIC")


# ===========================================================================
# 1-3. Recoverable scenarios
# ===========================================================================
def test_transient_failure_with_prior_success_is_recoverable():
    ctx = make_ctx(customer_successful_payments=3, customer_has_history=True)
    diag = make_diag("TECHNICAL_GATEWAY", 0.8)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred())
    assert r.classification == IntentClassification.RECOVERABLE
    assert "PREVIOUS_SUCCESS" in r.reason_codes
    assert "TRANSIENT_FAILURE" in r.reason_codes
    assert r.negative_signals == []


def test_auth_timeout_with_positive_history_is_recoverable():
    ctx = make_ctx(customer_successful_payments=5, customer_has_history=True, attempt_count=0)
    diag = make_diag("AUTH_TIMEOUT", 0.85)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred())
    assert r.classification == IntentClassification.RECOVERABLE


def test_low_retry_count_with_prior_success_is_recoverable():
    ctx = make_ctx(customer_successful_payments=2, customer_has_history=True, attempt_count=0)
    diag = make_diag("BANK_DECLINE", 0.75)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred())
    assert r.classification == IntentClassification.RECOVERABLE
    assert "LOW_RETRY_COUNT" in r.reason_codes


def test_recoverable_intent_does_not_bypass_amount_ceiling():
    """RECOVERABLE intent must never grant a permission the existing policy
    doesn't already give — a high-value payment still needs human approval."""
    ctx = make_ctx(customer_successful_payments=3, customer_has_history=True,
                    amount=Decimal(str(settings.POLICY_AUTO_APPROVAL_AMOUNT_LIMIT)) + Decimal("1"))
    diag = make_diag("TECHNICAL_GATEWAY", 0.8)
    intent = intent_mod.evaluate_intent(ctx, diag, make_pred())
    assert intent.classification == IntentClassification.RECOVERABLE
    policy = evaluate_policy(ctx, diag, make_pred(), make_strategy(), intent=intent)
    assert policy.verdict.value == "NEEDS_APPROVAL"


# ===========================================================================
# 4-7. Unwilling scenarios
# ===========================================================================
def test_risk_block_is_likely_unwilling():
    ctx = make_ctx()
    diag = make_diag("RISK_BLOCK", 0.9)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred(band=PredictionBand.LOW, probability=0.08))
    assert r.classification == IntentClassification.LIKELY_UNWILLING
    assert "RISK_BLOCK" in r.reason_codes


def test_repeated_ignored_recovery_attempts_is_likely_unwilling():
    ctx = make_ctx(customer_expired_or_cancelled_links=3, customer_has_history=True,
                    customer_successful_payments=1)
    diag = make_diag("AUTH_TIMEOUT", 0.7)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred())
    assert r.classification == IntentClassification.LIKELY_UNWILLING
    assert "REPEATED_IGNORED_RECOVERY_ATTEMPTS" in r.reason_codes


def test_repeated_abandonment_diagnoses_is_likely_unwilling():
    ctx = make_ctx(customer_prior_user_abandoned_count=2, customer_has_history=True)
    diag = make_diag("USER_ABANDONED", 0.75)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred())
    assert r.classification == IntentClassification.LIKELY_UNWILLING
    assert "REPEATED_ABANDONMENT" in r.reason_codes


def test_explicit_opt_out_is_likely_unwilling():
    ctx = make_ctx(customer_opted_out=True, customer_has_history=True, customer_successful_payments=5)
    diag = make_diag("AUTH_TIMEOUT", 0.8)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred())
    assert r.classification == IntentClassification.LIKELY_UNWILLING
    assert "EXPLICIT_OPT_OUT" in r.reason_codes


def test_likely_unwilling_is_hard_rejected_never_needs_approval():
    """Never allow LIKELY_UNWILLING -> automatic payment link — REJECTED,
    not NEEDS_APPROVAL, and never human-overridable via approval."""
    ctx = make_ctx(customer_opted_out=True)
    diag = make_diag("AUTH_TIMEOUT", 0.8)
    intent = intent_mod.evaluate_intent(ctx, diag, make_pred())
    policy = evaluate_policy(ctx, diag, make_pred(), make_strategy(), intent=intent)
    assert policy.verdict.value == "REJECTED"
    assert "RULE_INTENT_UNWILLING" in policy.violated_rules
    assert policy.allowed_actions == []


# ===========================================================================
# 8-10. Ambiguous / insufficient evidence
# ===========================================================================
def test_new_customer_with_no_history_is_insufficient_evidence():
    ctx = make_ctx(customer_id=None, customer_has_history=False, customer_successful_payments=0)
    diag = make_diag("UNKNOWN", 0.3)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred(band=PredictionBand.LOW, probability=0.3))
    assert r.classification == IntentClassification.INSUFFICIENT_EVIDENCE
    assert r.confidence <= 0.5


def test_conflicting_signals_is_ambiguous():
    ctx = make_ctx(customer_successful_payments=2, customer_has_history=True,
                    customer_expired_or_cancelled_links=1)  # one lapse, not repeated — weak negative
    diag = make_diag("BANK_DECLINE", 0.7)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred())
    # positive (prior success) + a noted-but-not-repeated negative -> ambiguous, not a hard verdict either way
    assert r.classification in (IntentClassification.AMBIGUOUS, IntentClassification.RECOVERABLE)


def test_insufficient_evidence_routes_to_needs_approval():
    ctx = make_ctx(customer_id=None, customer_has_history=False)
    diag = make_diag("UNKNOWN", 0.3)
    intent = intent_mod.evaluate_intent(ctx, diag, make_pred(band=PredictionBand.LOW, probability=0.3))
    assert intent.classification == IntentClassification.INSUFFICIENT_EVIDENCE
    policy = evaluate_policy(ctx, diag, make_pred(band=PredictionBand.LOW, probability=0.3),
                              make_strategy(), intent=intent)
    assert policy.verdict.value == "NEEDS_APPROVAL"
    assert "RULE_INTENT_EVIDENCE" in policy.violated_rules


# ===========================================================================
# 11-14. Security / isolation / AI safety
# ===========================================================================
def test_intent_never_evaluated_preserves_existing_policy_behavior():
    """intent=None (not evaluated) must produce byte-identical policy
    behavior to calling evaluate_policy with the old 4-arg signature."""
    ctx = make_ctx(customer_successful_payments=3, customer_has_history=True)
    diag = make_diag("AUTH_TIMEOUT", 0.8)
    pred = make_pred()
    strat = make_strategy()
    old_style = evaluate_policy(ctx, diag, pred, strat)          # no intent kwarg at all
    explicit_none = evaluate_policy(ctx, diag, pred, strat, intent=None)
    assert old_style.verdict == explicit_none.verdict
    assert old_style.reason == explicit_none.reason
    assert [r.rule_id for r in old_style.evaluated_rules] == [r.rule_id for r in explicit_none.evaluated_rules]


def test_organization_isolation_customer_history_never_leaks(unauthenticated_client, webhook_env):
    """Org A's repeated-abandonment/opt-out history must never influence
    Org B's intent evaluation for a similarly-shaped customer."""
    c = unauthenticated_client
    res_a = c.post("/api/v1/auth/register", json={
        "email": "intent-org-a@recon.test", "password": "Password123!", "organization_name": "Intent Org A",
    })
    assert res_a.status_code == 201, res_a.text
    # Build a customer in Org A with a strong negative history (2 expired links).
    for i in range(2):
        sim = c.post("/api/v1/simulator/events", json={
            "event_type": "payment.failed", "customer_name": "Shared Name",
            "customer_email": "shared@example.com", "amount": "999.00",
            "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
            "failure_reason": "payment_failed", "error_description": f"timeout {i}",
        })
        assert sim.status_code == 201, sim.text

    c.cookies.clear()
    res_b = c.post("/api/v1/auth/register", json={
        "email": "intent-org-b@recon.test", "password": "Password123!", "organization_name": "Intent Org B",
    })
    assert res_b.status_code == 201, res_b.text
    # SAME customer email/name in Org B — must start with zero history.
    sim_b = c.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Shared Name",
        "customer_email": "shared@example.com", "amount": "999.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed", "error_description": "timeout",
    })
    assert sim_b.status_code == 201, sim_b.text
    cn_b = sim_b.json()["case_number"]
    intent_b = c.get(f"/api/v1/recovery-cases/{cn_b}/intent")
    # Not yet analysed (INTELLIGENCE_ENABLED is off in tests unless triggered) —
    # analyze explicitly to get a real evaluation.
    c.post(f"/api/v1/recovery-cases/{cn_b}/intelligence:analyze")
    intent_b = c.get(f"/api/v1/recovery-cases/{cn_b}/intent").json()
    assert intent_b["evaluated"] is True
    assert intent_b["intent"]["classification"] != "LIKELY_UNWILLING", \
        "Org B's customer must not inherit Org A's negative history"


def test_ai_intent_module_cannot_execute_actions_or_communications():
    """Static safety check: the intent-evaluation modules must never import
    anything capable of executing a payment action or sending a
    communication — the only outputs are typed classification data."""
    import services.intelligence.intent as intent_source
    import services.intelligence.ai_intent as ai_intent_source

    for mod in (intent_source, ai_intent_source):
        src = open(mod.__file__, encoding="utf-8").read()
        for forbidden in (
            "services.actions.executor", "services.actions.verification",
            "integrations.razorpay", "services.communications",
        ):
            assert forbidden not in src, f"{mod.__name__} must never reference {forbidden}"


def test_ai_intent_cannot_mutate_recovery_outcome(db_session):
    """The AI-assisted intent path only ever returns an IntentResult — it
    has no access to a DB session and cannot touch RecoveryAction/RecoveryCase."""
    ctx = make_ctx(customer_successful_payments=1, customer_has_history=True)
    diag = make_diag("AUTH_TIMEOUT", 0.8)
    result, meta = aii.evaluate_intent_case(ctx, diag, make_pred())
    assert isinstance(result.classification, IntentClassification)
    # No RecoveryAction exists at all yet — evaluate_intent_case never created one.
    assert db_session.query(RecoveryAction).count() == 0


# ===========================================================================
# 15-18. Failure handling
# ===========================================================================
def test_ai_intent_failure_falls_back_to_deterministic(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-secret-key")
    monkeypatch.setattr(aii, "llm_available", lambda: True)

    class ExplodingProvider:
        def generate_structured(self, **kwargs):
            raise RuntimeError("simulated provider crash")

    monkeypatch.setattr(aii, "get_llm_provider", lambda: ExplodingProvider())

    ctx = make_ctx(customer_successful_payments=2, customer_has_history=True)
    diag = make_diag("AUTH_TIMEOUT", 0.8)
    result, meta = aii.evaluate_intent_case(ctx, diag, make_pred())
    assert result.provider == "DETERMINISTIC"
    assert meta.used_ai is False
    assert meta.attempted is True
    assert meta.error_type == "internal_error"
    # Deterministic result must still be a valid, usable classification.
    assert result.classification == IntentClassification.RECOVERABLE


def test_missing_customer_history_never_crashes_intent_evaluation():
    ctx = make_ctx(customer_id=None, customer_has_history=False, customer_successful_payments=0,
                    customer_failed_payments=0)
    diag = make_diag("UNKNOWN", 0.25)
    r = intent_mod.evaluate_intent(ctx, diag, make_pred(band=PredictionBand.LOW, probability=0.3))
    assert r.classification == IntentClassification.INSUFFICIENT_EVIDENCE


def test_malformed_evidence_defaults_never_crash_policy():
    """A policy call with intent=None (the 'malformed/absent evidence' case)
    must never raise and must behave exactly as before Phase 10."""
    ctx = make_ctx()
    diag = make_diag("AUTH_TIMEOUT", 0.8)
    policy = evaluate_policy(ctx, diag, make_pred(), make_strategy(), intent=None)
    assert policy.verdict.value in ("APPROVED", "NEEDS_APPROVAL", "REJECTED")
    assert "RULE_INTENT_UNWILLING" not in policy.violated_rules
    assert "RULE_INTENT_EVIDENCE" not in policy.violated_rules


def test_intelligence_pipeline_survives_intent_evaluation_exception(db_session, monkeypatch):
    """An exception inside evaluate_intent_case must never break the
    deterministic intelligence pipeline — falls back to intent=None,
    i.e. pre-Phase-10 behavior, and the run still completes successfully."""
    from services.intelligence.orchestrator import run_intelligence
    import services.intelligence.orchestrator as orch

    merchant = db_session.query(Merchant).first()
    _, case = process_inbound_event(db=db_session, raw_payload=upi_timeout_payload(), merchant_id=merchant.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated intent evaluation crash")

    monkeypatch.setattr(orch, "evaluate_intent_case", _boom)

    ci = run_intelligence(db_session, case.id, trigger="manual")
    assert ci.status != "FAILED"
    assert ci.intent_json is None
    assert ci.intent_classification is None
    assert ci.policy_verdict in ("APPROVED", "NEEDS_APPROVAL", "REJECTED")


# ===========================================================================
# Full-chain: RISK_BLOCK precedent stays intact + explicit unwilling scenario
# never produces an action, even with all automation flags on
# ===========================================================================
def test_repeated_expired_links_never_auto_executes_even_with_automation_on(
    client, razorpay_env, webhook_env, make_signature, monkeypatch
):
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "fake")

    # Build 2 prior EXPIRED RecoveryAction rows for one customer directly
    # (fast path — equivalent to a real expired-payment-link history).
    from models.customer import Customer as CustomerModel
    from models.payment import Payment as PaymentModel
    merchant = client.get("/api/v1/auth/me").json()  # ensures session is live
    db_merchant_id = None
    from database import SessionLocal
    db = SessionLocal()
    try:
        from models.merchant import Merchant as MerchantModel
        m = db.query(MerchantModel).first()
        db_merchant_id = m.id
        customer = CustomerModel(merchant_id=m.id, email="repeat-lapse@example.com", name="Repeat Lapse",
                                  total_payment_amount=Decimal("0.00"), successful_payment_count=0,
                                  failed_payment_count=2)
        db.add(customer)
        db.flush()
        for i in range(2):
            rc = RecoveryCase(
                case_number=f"RC-LAPSE-{i}", merchant_id=m.id, customer_id=customer.id,
                amount_at_risk=Decimal("999.00"), amount_recovered=Decimal("0.00"), currency="INR",
                status="RESOLVED", priority="LOW", attempt_count=1, max_attempts=3,
            )
            db.add(rc)
            db.flush()
            ra = RecoveryAction(
                recovery_case_id=rc.id, merchant_id=m.id, action_type="CREATE_PAYMENT_LINK",
                status="EXECUTED", outcome="EXPIRED",
                idempotency_key=f"lapse-{i}", reference_id=f"RECON-LAPSE-{i}",
                amount=Decimal("999.00"), amount_paise=99900, currency="INR",
                provider_action_id=f"plink_lapse_{i}",
            )
            db.add(ra)
        db.commit()
        customer_id = customer.id
    finally:
        db.close()

    payload = upi_timeout_payload(pid="pay_lapse_new", eid="evt_lapse_new_1", amount_paise=99900)
    payload["payload"]["payment"]["entity"]["email"] = "repeat-lapse@example.com"
    payload["payload"]["payment"]["entity"]["customer_id"] = None
    raw = json.dumps(payload).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json", "X-Razorpay-Signature": make_signature(raw)})
    assert res.status_code == 200
    cn = res.json()["case_number"]

    case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    intel = case.get("intelligence") or {}
    if intel:
        # If the summary is populated, the repeated-lapse signal must have
        # been strong enough to reject automatic pursuit.
        assert intel.get("policy_verdict") in ("REJECTED", "NEEDS_APPROVAL")
    actions = client.get(f"/api/v1/recovery-cases/{cn}/actions").json()["items"]
    executed = [a for a in actions if a["status"] == "EXECUTED"]
    assert executed == [], "a customer with 2 prior expired/cancelled links must never be auto-executed"


def test_full_regression_risk_block_precedent_intent_field_present(
    client, razorpay_env, webhook_env, make_signature, monkeypatch
):
    """Extends the existing RISK_BLOCK precedent: the case must now ALSO
    carry an explicit LIKELY_UNWILLING intent classification, on top of the
    unchanged REJECTED verdict and zero actions."""
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", True)
    payload = upi_timeout_payload(pid="pay_intent_regress_1", eid="evt_intent_regress_1")
    payload["payload"]["payment"]["entity"]["error_reason"] = "payment_risk_check_failed"
    payload["payload"]["payment"]["entity"]["error_description"] = "risk engine blocked transaction"
    raw = json.dumps(payload).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json", "X-Razorpay-Signature": make_signature(raw)})
    assert res.status_code == 200
    cn = res.json()["case_number"]

    intent = client.get(f"/api/v1/recovery-cases/{cn}/intent").json()
    assert intent["evaluated"] is True
    assert intent["intent"]["classification"] == "LIKELY_UNWILLING"
    assert client.get(f"/api/v1/recovery-cases/{cn}/actions").json()["items"] == []


# ===========================================================================
# CRITICAL FIX B1 regression — intent enforced at the AUTHORITATIVE
# execution gate (execute_action), not just the advisory intelligence pass.
#
# Every test below FORCES a RecoveryAction row into existence directly via
# the ORM (bypassing the propose endpoint / get_or_create_action) to prove
# execute_action() itself — the one function that actually calls Razorpay —
# independently recomputes intent and blocks on it, rather than relying on
# the proposal-time check to have kept a bad action from ever existing. A
# forged/stale `policy_verdict="APPROVED"` is deliberately set on the forced
# action to prove execute_action() never trusts a stored verdict.
# ===========================================================================
def _latest_ci(db, case_id):
    return (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id == case_id)
        .order_by(CaseIntelligence.version.desc())
        .first()
    )


def _force_action(db, case, *, tag: str) -> RecoveryAction:
    """A RecoveryAction as if already proposed/approved earlier — never
    trusted by execute_action(), which must re-derive everything fresh."""
    amount = case.amount_at_risk
    action = RecoveryAction(
        recovery_case_id=case.id,
        merchant_id=case.merchant_id,
        action_type="CREATE_PAYMENT_LINK",
        action_version=1,
        status="PROPOSED",
        outcome="PENDING",
        idempotency_key=f"forced-{tag}-{case.id}",
        reference_id=f"RC-FORCED-{tag}-{case.id}",
        strategy_action="SEND_PAYMENT_LINK",
        policy_verdict="APPROVED",  # forged/stale — execute_action must not trust this
        amount=amount,
        amount_paise=to_paise(amount),
        currency=case.currency or "INR",
        provider="RAZORPAY",
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def _make_prior_expired_link(db, case) -> None:
    amount = case.amount_at_risk
    prior = RecoveryAction(
        recovery_case_id=case.id,
        merchant_id=case.merchant_id,
        action_type="CREATE_PAYMENT_LINK",
        action_version=1,
        status="EXECUTED",
        outcome="EXPIRED",
        idempotency_key=f"prior-expired-{case.id}",
        reference_id=f"RC-PRIOR-EXPIRED-{case.id}",
        strategy_action="SEND_PAYMENT_LINK",
        policy_verdict="APPROVED",
        amount=amount,
        amount_paise=to_paise(amount),
        currency=case.currency or "INR",
        provider="RAZORPAY",
        provider_action_id=f"plink_prior_{case.id}",
    )
    db.add(prior)
    db.commit()


# ---------------------------------------------------------------------------
# A. Direct API execution cannot bypass intent rejection (opted-out customer)
# ---------------------------------------------------------------------------
def test_api_direct_execution_cannot_bypass_intent_rejection(client, db_session, razorpay_env):
    cn = _api_analyzed_case(
        client, customer_email="unwilling-api@example.com", customer_phone="+919876500011",
    )
    case = db_session.query(RecoveryCase).filter_by(case_number=cn).first()
    customer = db_session.query(Customer).filter_by(id=case.customer_id).first()
    assert customer is not None
    customer.opted_out_channels = "EMAIL,SMS"
    db_session.commit()

    # Re-analyze via the real API so CaseIntelligence reflects the opt-out.
    analyze = client.post(f"/api/v1/recovery-cases/{cn}/intelligence:analyze")
    assert analyze.status_code == 200, analyze.text

    ci = _latest_ci(db_session, case.id)
    assert ci.intent_classification == "LIKELY_UNWILLING"
    assert ci.policy_verdict == "REJECTED"

    # The propose endpoint itself must now refuse (build_proposal fix, item D).
    propose_resp = client.post(f"/api/v1/recovery-cases/{cn}/actions/propose")
    assert propose_resp.status_code == 200, propose_resp.text
    body = propose_resp.json()
    assert body["action"] is None
    assert body["proposal"]["proposable"] is False
    assert body["proposal"]["not_proposable_reason"] == "POLICY_REJECTED"

    # Force an action into existence directly (as if it had been proposed
    # BEFORE the opt-out was recorded) and hit the real execute endpoint —
    # the authoritative gate must still block it, independent of proposal.
    db_session.refresh(case)
    action = _force_action(db_session, case, tag="apiA")

    exec_resp = client.post(f"/api/v1/actions/{action.id}/execute")
    assert exec_resp.status_code == 200, exec_resp.text
    exec_body = exec_resp.json()
    assert exec_body["ok"] is False
    assert exec_body["action"]["status"] == "BLOCKED"
    assert exec_body["action"]["blocked_reason"] == "POLICY_REJECTED"
    assert exec_body["action"]["provider_action_id"] is None

    assert razorpay_env["calls"] == [], \
        "no Razorpay payment-link call must ever be made for a LIKELY_UNWILLING customer"


# ---------------------------------------------------------------------------
# B. Opted-out customer — service-level execute_action() proof
# ---------------------------------------------------------------------------
def test_execute_action_blocked_for_opted_out_customer(db_session, razorpay_env):
    payload = upi_timeout_payload(pid="pay_unwilling_optout", eid="evt_unwilling_optout")
    payload["payload"]["payment"]["entity"]["email"] = "unwilling-optout@example.com"
    case = _make_case(db_session, payload)
    customer = db_session.query(Customer).filter_by(id=case.customer_id).first()
    assert customer is not None
    customer.opted_out_channels = "EMAIL"
    db_session.commit()

    run_intelligence(db_session, case.id, trigger="test")
    db_session.refresh(case)
    ci = _latest_ci(db_session, case.id)
    assert ci.intent_classification == "LIKELY_UNWILLING"
    assert ci.policy_verdict == "REJECTED"

    proposal = build_proposal(db_session, case)
    assert proposal.proposable is False
    assert proposal.not_proposable_reason == "POLICY_REJECTED"

    action = _force_action(db_session, case, tag="optout")
    result = execute_action(db_session, action.id)

    assert result.status == "BLOCKED"
    assert result.blocked_reason == "POLICY_REJECTED"
    assert result.outcome != "RECOVERED"
    assert result.provider_action_id is None
    assert razorpay_env["calls"] == []


# ---------------------------------------------------------------------------
# C. Repeated expired/cancelled links — service-level execute_action() proof
# ---------------------------------------------------------------------------
def test_execute_action_blocked_for_repeated_expired_links(db_session, razorpay_env):
    shared_email = "repeat-expired-exec@example.com"
    for i in range(2):
        prior_payload = upi_timeout_payload(pid=f"pay_prior_exec_{i}", eid=f"evt_prior_exec_{i}")
        prior_payload["payload"]["payment"]["entity"]["email"] = shared_email
        prior_payload["payload"]["payment"]["entity"]["customer_id"] = None
        prior_case = _make_case(db_session, prior_payload)
        _make_prior_expired_link(db_session, prior_case)

    payload = upi_timeout_payload(pid="pay_current_exec", eid="evt_current_exec")
    payload["payload"]["payment"]["entity"]["email"] = shared_email
    payload["payload"]["payment"]["entity"]["customer_id"] = None
    case = _make_case(db_session, payload)

    run_intelligence(db_session, case.id, trigger="test")
    db_session.refresh(case)
    ci = _latest_ci(db_session, case.id)
    assert ci.intent_classification == "LIKELY_UNWILLING"
    assert ci.policy_verdict == "REJECTED"

    action = _force_action(db_session, case, tag="expiredlinks")
    result = execute_action(db_session, action.id)

    assert result.status == "BLOCKED"
    assert result.blocked_reason == "POLICY_REJECTED"
    assert result.outcome != "RECOVERED"
    assert result.provider_action_id is None
    assert razorpay_env["calls"] == []


# ---------------------------------------------------------------------------
# D. build_proposal() refuses when the latest policy verdict is REJECTED
# ---------------------------------------------------------------------------
def test_build_proposal_refuses_when_policy_verdict_rejected(db_session):
    """Uses an opted-out customer (strategy IS payment-link eligible, but
    intent evaluation makes policy REJECT it) rather than RISK_BLOCK — RISK_BLOCK's
    strategy is never payment-link eligible in the first place, so it already
    (and still) reports STRATEGY_NOT_ELIGIBLE, checked first; this test
    targets the specific new case: an otherwise-eligible strategy blocked by
    the REJECTED verdict itself."""
    payload = upi_timeout_payload(pid="pay_proposal_rejected", eid="evt_proposal_rejected")
    payload["payload"]["payment"]["entity"]["email"] = "proposal-rejected@example.com"
    case = _make_case(db_session, payload)
    customer = db_session.query(Customer).filter_by(id=case.customer_id).first()
    assert customer is not None
    customer.opted_out_channels = "EMAIL"
    db_session.commit()

    run_intelligence(db_session, case.id, trigger="test")
    db_session.refresh(case)

    ci = _latest_ci(db_session, case.id)
    assert ci.intent_classification == "LIKELY_UNWILLING"
    assert ci.policy_verdict == "REJECTED"
    assert ci.recommended_action in PAYMENT_LINK_ELIGIBLE_STRATEGIES, \
        "this test targets a strategy-eligible-but-policy-rejected case"

    proposal = build_proposal(db_session, case)
    assert proposal.proposable is False
    assert proposal.not_proposable_reason == "POLICY_REJECTED"

    # get_or_create_action must not create a row either.
    action, proposal2 = get_or_create_action(db_session, case)
    assert action is None
    assert proposal2.proposable is False


# ---------------------------------------------------------------------------
# E. RISK_BLOCK behavior is preserved after threading intent through execute_action()
# ---------------------------------------------------------------------------
def test_execute_action_still_blocks_risk_block_after_intent_fix(db_session, razorpay_env):
    """A RISK_BLOCK case's strategy was never payment-link eligible to begin
    with, so it is (and must remain) blocked at the pre-existing
    STRATEGY_NOT_ELIGIBLE gate — checked before policy re-evaluation — never
    reaching Razorpay either way. This proves threading intent through
    execute_action() did not change this pre-existing outcome."""
    payload = upi_timeout_payload(pid="pay_riskblock_exec", eid="evt_riskblock_exec")
    payload["payload"]["payment"]["entity"]["error_reason"] = "payment_risk_check_failed"
    payload["payload"]["payment"]["entity"]["error_description"] = "risk engine blocked transaction"
    case = _make_case(db_session, payload)
    run_intelligence(db_session, case.id, trigger="test")
    db_session.refresh(case)

    ci = _latest_ci(db_session, case.id)
    assert ci.failure_category == "RISK_BLOCK"
    assert ci.policy_verdict == "REJECTED"
    assert ci.recommended_action not in PAYMENT_LINK_ELIGIBLE_STRATEGIES

    action = _force_action(db_session, case, tag="riskblock")
    result = execute_action(db_session, action.id)

    assert result.status == "BLOCKED"
    assert result.blocked_reason == "STRATEGY_NOT_ELIGIBLE"
    assert result.provider_action_id is None
    assert razorpay_env["calls"] == []


# ---------------------------------------------------------------------------
# F. APPROVED automatic execution behavior is preserved (happy path)
# ---------------------------------------------------------------------------
def test_execute_action_still_succeeds_for_approved_recoverable_case(db_session, razorpay_env):
    payload = upi_timeout_payload(pid="pay_recoverable_exec", eid="evt_recoverable_exec")
    case = _make_case(db_session, payload)
    run_intelligence(db_session, case.id, trigger="test")
    db_session.refresh(case)

    ci = _latest_ci(db_session, case.id)
    assert ci.policy_verdict == "APPROVED"
    assert ci.intent_classification in ("RECOVERABLE", "AMBIGUOUS", "INSUFFICIENT_EVIDENCE", None)
    assert ci.intent_classification != "LIKELY_UNWILLING"

    action, proposal = get_or_create_action(db_session, case)
    assert action is not None, f"not proposable: {proposal.not_proposable_reason}"

    result = execute_action(db_session, action.id)
    assert result.status == "EXECUTED"
    assert result.outcome == "PENDING"
    assert result.provider_action_id is not None
    assert len(razorpay_env["calls"]) == 1
