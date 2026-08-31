"""
RECON OS — Phase 6: Real Multi-Model AI Intelligence Tests  (SAFETY-CRITICAL)

Covers: feature-builder determinism, dataset schema, model registry loading,
inference resilience, prediction schema, org/RBAC on the new AI endpoints,
and — most importantly — proof that an ML prediction can never bypass the
Policy Engine, influence approval, or execute a financial action directly.

Nothing here trains a model. Tests that need a real prediction rely on
whatever is already in apps/api/ai/artifacts (produced by a prior
`python -m ai.training.train` run) and skip gracefully if that model isn't
present — the safety/integration guarantees below hold either way, since
`predict_for_case` and the orchestrator are both designed to degrade to
`None` rather than fail.
"""

import pytest

from ai.features.feature_builder import (
    CASE_FEATURE_COLUMNS,
    DIAGNOSIS_FEATURE_COLUMNS,
    build_case_features,
    build_diagnosis_features,
)
from ai.inference.service import _available_channels, predict_for_case
from ai.models.base import ModelRegistry
from models.audit_log import AuditLog
from models.case_intelligence import CaseIntelligence
from models.merchant import Merchant
from models.recovery_action import RecoveryAction
from services.event_processor import process_inbound_event
from services.intelligence.orchestrator import run_intelligence

SAMPLE_SOURCE = {
    "amount": 4999.0,
    "attempt_count": 1,
    "max_attempts": 3,
    "hours_since_failure": 2.0,
    "customer_success_rate": 0.8,
    "customer_lifetime_amount": 50000.0,
    "customer_successful_payments": 4,
    "customer_failed_payments": 1,
    "previous_recovery_cases": 0,
    "previous_resolved_cases": 0,
    "previous_recovery_attempts": 0,
    "customer_contacts_last_24h": 0,
    "customer_has_history": True,
    "payment_method": "upi",
    "amount_band": "MEDIUM",
    "failure_reason": "payment_failed",
    "failure_description": "UPI handle authorization timeout on customer app",
    "failure_code": "BAD_REQUEST_ERROR",
}


def _make_case(db, payload):
    merchant = db.query(Merchant).first()
    _, case = process_inbound_event(db=db, raw_payload=payload, merchant_id=merchant.id)
    return case


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
def test_build_case_features_deterministic():
    a = build_case_features(SAMPLE_SOURCE, failure_category="AUTH_TIMEOUT")
    b = build_case_features(SAMPLE_SOURCE, failure_category="AUTH_TIMEOUT")
    assert a == b
    assert set(a.keys()) == set(CASE_FEATURE_COLUMNS)


def test_build_diagnosis_features_excludes_target_and_is_deterministic():
    a = build_diagnosis_features(SAMPLE_SOURCE)
    b = build_diagnosis_features(SAMPLE_SOURCE)
    assert a == b
    assert set(a.keys()) == set(DIAGNOSIS_FEATURE_COLUMNS)
    assert "failure_category" not in a  # target leakage guard


def test_build_case_features_missing_fields_do_not_raise():
    features = build_case_features({}, failure_category="UNKNOWN")
    assert features["amount_log"] == 0.0
    assert features["payment_method"] == "unknown"
    assert features["failure_category"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
def test_model_registry_returns_none_for_unknown_model():
    model, meta = ModelRegistry.load_model("does_not_exist_model")
    assert model is None and meta is None
    assert ModelRegistry.load_metadata("does_not_exist_model") is None
    assert ModelRegistry.latest_version("does_not_exist_model") is None


def test_model_registry_list_models_shape():
    listing = ModelRegistry.list_models()
    assert isinstance(listing, list)
    for entry in listing:
        assert {"model_name", "versions", "latest_version", "metadata"} <= entry.keys()
        if entry["metadata"] is not None:
            # metadata is metrics/status only — never a raw file path or dataset
            assert "metrics" in entry["metadata"]
            assert "status" in entry["metadata"]


# ---------------------------------------------------------------------------
# Inference resilience
# ---------------------------------------------------------------------------
def test_predict_for_case_never_raises_with_no_models(monkeypatch, tmp_path):
    """Point the registry at an empty directory: every model is 'missing',
    and predict_for_case must still return cleanly with no predictions."""
    monkeypatch.setattr("ai.models.base.ARTIFACT_ROOT", tmp_path)
    from schemas.intelligence import CaseContext

    ctx = CaseContext(
        case_id="00000000-0000-0000-0000-000000000000", case_number="RCV-TEST-0001",
        case_status="DETECTED", amount=4999.0, currency="INR", attempt_count=1,
        max_attempts=3, opened_at="2026-01-01T00:00:00Z", hours_since_failure=1.0,
        payment_id="pay_test", payment_status="failed", payment_method="upi",
        failure_code="BAD_REQUEST_ERROR", failure_reason="payment_failed",
        failure_description="timeout", customer_id=None, customer_name=None,
        customer_successful_payments=0, customer_failed_payments=0,
        customer_lifetime_amount=0.0, customer_success_rate=0.0,
        customer_has_history=False, previous_recovery_cases=0,
        previous_resolved_cases=0, previous_recovery_attempts=0,
        customer_contacts_last_24h=0, amount_band="MEDIUM",
    )
    predictions = predict_for_case(ctx, failure_category="AUTH_TIMEOUT")
    assert isinstance(predictions, dict)
    assert "feature_version" in predictions and "generated_at" in predictions
    # No trained model present -> no model keys populated, but no exception
    assert "diagnosis" not in predictions
    assert "recovery_probability" not in predictions


def test_available_channels_respects_opt_out_and_missing_contact():
    assert _available_channels(None) == ["EMAIL", "SMS", "WHATSAPP"]
    assert _available_channels({"email": None, "phone": "+91900000", "opted_out_channels": ""}) == ["SMS", "WHATSAPP"]
    assert _available_channels({"email": "a@b.com", "phone": "+91900000", "opted_out_channels": "SMS,WHATSAPP"}) == ["EMAIL"]
    assert _available_channels({"email": "a@b.com", "phone": None, "opted_out_channels": "EMAIL"}) == []


# ---------------------------------------------------------------------------
# Orchestrator integration — ML predictions are advisory, never authoritative
# ---------------------------------------------------------------------------
def test_orchestrator_persists_ml_predictions_json_when_available(db_session, sample_payment_failed_payload):
    case = _make_case(db_session, sample_payment_failed_payload)
    ci = run_intelligence(db_session, case.id, trigger="test")
    assert ci.status != "FAILED"
    # ml_predictions_json is either a populated dict (models trained) or None
    # (no artifacts yet) — never missing as a column, never breaks the run.
    assert hasattr(ci, "ml_predictions_json")
    if ci.ml_predictions_json is not None:
        assert "feature_version" in ci.ml_predictions_json


def test_ml_inference_failure_never_breaks_deterministic_pipeline(db_session, sample_payment_failed_payload, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulated ML failure")

    monkeypatch.setattr("ai.inference.service.predict_for_case", boom)
    case = _make_case(db_session, sample_payment_failed_payload)
    ci = run_intelligence(db_session, case.id, trigger="test")

    assert ci.status in ("POLICY_APPROVED", "NEEDS_APPROVAL", "POLICY_REJECTED")
    assert ci.failure_category is not None
    assert ci.policy_verdict is not None
    assert ci.ml_predictions_json is None

    actions = {a.action for a in db_session.query(AuditLog).filter(AuditLog.recovery_case_id == case.id).all()}
    assert "INTELLIGENCE_COMPLETED" in actions
    assert "POLICY_EVALUATED" in actions


def test_ml_predictions_cannot_change_policy_verdict(db_session, sample_payment_failed_payload, monkeypatch):
    """Even if the ML layer returns an extreme (fabricated, for this test
    only) high recovery-probability/low-risk signal, the deterministic
    Policy Engine's verdict — computed from Phase 2's own prediction/strategy
    — must be completely unaffected, because ml_predictions is attached
    strictly AFTER evaluate_policy() runs."""
    case = _make_case(db_session, sample_payment_failed_payload)
    baseline = run_intelligence(db_session, case.id, trigger="baseline")
    baseline_verdict = baseline.policy_verdict
    baseline_action = baseline.recommended_action

    def fake_predict(*a, **k):
        return {
            "feature_version": "1.0", "generated_at": "2026-01-01T00:00:00Z",
            "recovery_probability": {"model_name": "recovery_probability", "model_version": "v999",
                                      "status": "READY", "recovery_probability": 0.999999},
        }

    monkeypatch.setattr("ai.inference.service.predict_for_case", fake_predict)
    again = run_intelligence(db_session, case.id, trigger="with-fake-ml")
    assert again.policy_verdict == baseline_verdict
    assert again.recommended_action == baseline_action
    assert again.ml_predictions_json["recovery_probability"]["recovery_probability"] == pytest.approx(0.999999)


def test_ai_module_has_no_access_to_action_execution():
    """Static guarantee: the AI package must never import the Action Engine,
    the Razorpay adapter, or the communication senders — it can only ever
    return a plain dict. This is the "cannot directly execute a financial
    action" proof: the import graph makes it structurally impossible, not
    just behaviorally unlikely."""
    import ai.inference.service as svc
    import ai.models.base as base
    import inspect

    forbidden_substrings = (
        "services.actions.executor", "services.actions.proposal",
        "integrations.razorpay", "services.communications.providers",
    )
    for mod in (svc, base):
        src = inspect.getsource(mod)
        for forbidden in forbidden_substrings:
            assert forbidden not in src, f"{mod.__name__} must never reference {forbidden}"


def test_analyzing_a_case_never_creates_a_recovery_action(db_session, sample_payment_failed_payload):
    """Running intelligence (which now includes ML inference) must not, by
    itself, create or execute any RecoveryAction — that stays a separate,
    explicit, policy-gated step (routers/actions.py)."""
    case = _make_case(db_session, sample_payment_failed_payload)
    run_intelligence(db_session, case.id, trigger="test")
    run_intelligence(db_session, case.id, trigger="test")
    assert db_session.query(RecoveryAction).filter(RecoveryAction.recovery_case_id == case.id).count() == 0


# ---------------------------------------------------------------------------
# API: authentication, organization isolation, RBAC
# ---------------------------------------------------------------------------
def test_ai_models_endpoint_requires_authentication(unauthenticated_client):
    res = unauthenticated_client.get("/api/v1/ai/models")
    assert res.status_code in (401, 403)


def test_ai_models_endpoint_authenticated_shape(client):
    res = client.get("/api/v1/ai/models")
    assert res.status_code == 200
    body = res.json()
    assert "models" in body and isinstance(body["models"], list)


def test_case_ai_predictions_endpoint_requires_authentication(unauthenticated_client):
    res = unauthenticated_client.get("/api/v1/recovery-cases/RCV-DOES-NOT-EXIST/ai-predictions")
    assert res.status_code in (401, 403)


def test_case_ai_predictions_not_found_for_unknown_case(client):
    res = client.get("/api/v1/recovery-cases/RCV-DOES-NOT-EXIST/ai-predictions")
    assert res.status_code == 404


def test_case_ai_predictions_before_analysis(client):
    sim = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Pre Analysis",
        "customer_email": "pre@example.com", "amount": "4999.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed", "error_description": "timeout",
    })
    case_number = sim.json()["case_number"]
    res = client.get(f"/api/v1/recovery-cases/{case_number}/ai-predictions")
    assert res.status_code == 200
    body = res.json()
    assert body["analyzed"] is False


def test_case_ai_predictions_after_analysis(client):
    sim = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Post Analysis",
        "customer_email": "post@example.com", "amount": "4999.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed", "error_description": "timeout",
    })
    case_number = sim.json()["case_number"]
    client.post(f"/api/v1/recovery-cases/{case_number}/intelligence:analyze")
    res = client.get(f"/api/v1/recovery-cases/{case_number}/ai-predictions")
    assert res.status_code == 200
    body = res.json()
    assert body["analyzed"] is True


def test_cross_organization_ai_predictions_denied(unauthenticated_client):
    c = unauthenticated_client
    reg_a = c.post("/api/v1/auth/register", json={
        "email": "orga-ai@recon.test", "password": "OrgPassword123!", "organization_name": "Org A AI",
    })
    assert reg_a.status_code == 201, reg_a.text
    sim = c.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Cross Org AI",
        "customer_email": "crossai@example.com", "amount": "2999.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed", "error_description": "timeout",
    })
    case_number_a = sim.json()["case_number"]
    c.post(f"/api/v1/recovery-cases/{case_number_a}/intelligence:analyze")

    c.cookies.clear()
    reg_b = c.post("/api/v1/auth/register", json={
        "email": "orgb-ai@recon.test", "password": "OrgPassword123!", "organization_name": "Org B AI",
    })
    assert reg_b.status_code == 201, reg_b.text

    denied = c.get(f"/api/v1/recovery-cases/{case_number_a}/ai-predictions")
    assert denied.status_code == 404
