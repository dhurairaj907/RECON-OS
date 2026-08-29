"""
RECON OS — Phase 2 (THINK) Orchestrator, Persistence, API & Pipeline Tests

Also re-verifies that the Phase 1 simulator and event ingestion are unaffected.
"""

from decimal import Decimal

import pytest

from config import settings
from models.audit_log import AuditLog
from models.case_intelligence import CaseIntelligence
from models.merchant import Merchant
from models.recovery_case import RecoveryCase
from services.event_processor import process_inbound_event
from services.intelligence.orchestrator import run_intelligence


def _make_case(db, payload):
    merchant = db.query(Merchant).first()
    _, case = process_inbound_event(db=db, raw_payload=payload, merchant_id=merchant.id)
    return case


# ---------------------------------------------------------------------------
# 14. Full orchestrator
# ---------------------------------------------------------------------------
def test_orchestrator_full_pipeline(db_session, sample_payment_failed_payload):
    case = _make_case(db_session, sample_payment_failed_payload)
    ci = run_intelligence(db_session, case.id, trigger="test")

    assert ci.status in ("POLICY_APPROVED", "NEEDS_APPROVAL", "POLICY_REJECTED")
    assert ci.provider == "DETERMINISTIC"
    assert ci.version == 1
    assert ci.failure_category is not None
    assert ci.recovery_probability is not None
    assert ci.prediction_band in ("LOW", "MEDIUM", "HIGH")
    assert ci.recommended_action is not None
    assert ci.policy_verdict in ("APPROVED", "NEEDS_APPROVAL", "REJECTED")
    for section in (ci.context_json, ci.diagnosis_json, ci.prediction_json,
                    ci.strategy_json, ci.policy_json):
        assert isinstance(section, dict) and section


# ---------------------------------------------------------------------------
# 15. Persistence
# ---------------------------------------------------------------------------
def test_intelligence_persisted_and_versioned(db_session, sample_payment_failed_payload):
    case = _make_case(db_session, sample_payment_failed_payload)
    run_intelligence(db_session, case.id, trigger="test")
    run_intelligence(db_session, case.id, trigger="test")
    run_intelligence(db_session, case.id, trigger="test")

    rows = (
        db_session.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id == case.id)
        .order_by(CaseIntelligence.version)
        .all()
    )
    assert [r.version for r in rows] == [1, 2, 3]
    # exactly one recovery case still exists (no duplication)
    assert db_session.query(RecoveryCase).count() == 1


# ---------------------------------------------------------------------------
# 16 & 17. Intelligence API + repeated analysis
# ---------------------------------------------------------------------------
def test_intelligence_api_get_before_and_after_analyze(client):
    sim = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed",
        "customer_name": "Rahul Sharma",
        "customer_email": "rahul.sharma@example.com",
        "amount": "4999.00",
        "payment_method": "upi",
        "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed",
        "error_description": "UPI handle authorization timeout on customer app",
    })
    assert sim.status_code == 201
    case_number = sim.json()["case_number"]

    before = client.get(f"/api/v1/recovery-cases/{case_number}/intelligence")
    assert before.status_code == 200
    assert before.json()["analyzed"] is False
    assert before.json()["status"] == "NOT_RUN"

    run = client.post(f"/api/v1/recovery-cases/{case_number}/intelligence:analyze")
    assert run.status_code == 200
    body = run.json()
    assert body["analyzed"] is True
    assert body["status"] == "POLICY_APPROVED"
    assert body["provider"] == "DETERMINISTIC"
    assert body["diagnosis"]["failure_category"] == "AUTH_TIMEOUT"
    assert 0.0 <= body["prediction"]["recovery_probability"] <= 1.0
    assert body["strategy"]["action"] == "RETRY_NOW"
    assert body["policy"]["verdict"] == "APPROVED"
    assert len(body["policy"]["evaluated_rules"]) >= 7

    after = client.get(f"/api/v1/recovery-cases/{case_number}/intelligence")
    assert after.json()["status"] == "POLICY_APPROVED"

    # repeated analysis is safe: new version, still one case
    again = client.post(f"/api/v1/recovery-cases/{case_number}/intelligence:analyze")
    assert again.status_code == 200
    assert int(again.json()["version"]) == 2
    assert client.get("/api/v1/recovery-cases").json()["total"] == 1


def test_intelligence_attached_to_recovery_case_detail(client):
    sim = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Acme Ltd",
        "customer_email": "finance@acme.test", "amount": "75000.00",
        "payment_method": "netbanking", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed",
        "error_description": "Corporate netbanking approval limit exceeded",
    })
    case_number = sim.json()["case_number"]
    client.post(f"/api/v1/recovery-cases/{case_number}/intelligence:analyze")

    detail = client.get(f"/api/v1/recovery-cases/{case_number}")
    assert detail.status_code == 200
    intel = detail.json()["intelligence"]
    assert intel is not None
    assert intel["policy_verdict"] == "NEEDS_APPROVAL"
    assert intel["risk_level"] == "HIGH"
    assert intel["provider"] == "DETERMINISTIC"

    # list endpoint also carries the summary + dashboard metrics populate
    listing = client.get("/api/v1/intelligence")
    assert listing.json()["total"] == 1
    dash = client.get("/api/v1/dashboard/metrics").json()
    assert dash["intelligence"]["cases_analyzed"] == 1
    assert dash["intelligence"]["needs_approval"] == 1


# ---------------------------------------------------------------------------
# 18. Audit trail
# ---------------------------------------------------------------------------
def test_intelligence_writes_audit_trail(db_session, sample_payment_failed_payload):
    case = _make_case(db_session, sample_payment_failed_payload)
    run_intelligence(db_session, case.id, trigger="test")

    actions = {
        a.action for a in db_session.query(AuditLog)
        .filter(AuditLog.recovery_case_id == case.id).all()
    }
    assert {
        "INTELLIGENCE_STARTED", "DIAGNOSIS_COMPLETED", "PREDICTION_COMPLETED",
        "STRATEGY_COMPLETED", "POLICY_EVALUATED", "INTELLIGENCE_COMPLETED",
    }.issubset(actions)

    actors = {
        a.actor for a in db_session.query(AuditLog)
        .filter(AuditLog.recovery_case_id == case.id).all()
    }
    assert {"RECON_ENGINE", "DIAGNOSIS_AGENT", "PREDICTION_AGENT",
            "STRATEGY_AGENT", "POLICY_ENGINE"}.issubset(actors)


def test_intelligence_failure_is_audited(db_session, sample_payment_failed_payload, monkeypatch):
    case = _make_case(db_session, sample_payment_failed_payload)

    def boom(*a, **k):
        raise RuntimeError("simulated diagnosis failure")

    monkeypatch.setattr("services.intelligence.orchestrator.diagnose", boom)
    ci = run_intelligence(db_session, case.id, trigger="test")
    assert ci.status == "FAILED"
    assert "simulated diagnosis failure" in (ci.error_message or "")

    actions = {
        a.action for a in db_session.query(AuditLog)
        .filter(AuditLog.recovery_case_id == case.id).all()
    }
    assert "INTELLIGENCE_STARTED" in actions
    assert "INTELLIGENCE_FAILED" in actions


# ---------------------------------------------------------------------------
# Pipeline integration — Phase 2 must not break Phase 1
# ---------------------------------------------------------------------------
def test_pipeline_runs_intelligence_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", True)
    sim = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Priya Patel",
        "customer_email": "priya@example.com", "amount": "4999.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed",
        "error_description": "UPI authorization timeout",
    })
    assert sim.status_code == 201
    case_number = sim.json()["case_number"]

    # Phase 1 still fully intact
    dash = client.get("/api/v1/dashboard/metrics").json()
    assert dash["events_processed"] == 1
    assert dash["active_recovery_cases"] == 1
    assert float(dash["revenue_at_risk"]) == 4999.00

    # Phase 2 ran automatically via the post-commit hook
    intel = client.get(f"/api/v1/recovery-cases/{case_number}/intelligence").json()
    assert intel["analyzed"] is True
    assert intel["status"] == "POLICY_APPROVED"


def test_pipeline_intelligence_failure_does_not_break_phase1(client, monkeypatch):
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", True)

    def boom(*a, **k):
        raise RuntimeError("intelligence exploded")

    monkeypatch.setattr(
        "services.intelligence.orchestrator.build_case_context", boom
    )

    sim = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Test User",
        "customer_email": "test@example.com", "amount": "8499.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed", "error_description": "timeout",
    })
    # Phase 1 succeeds regardless
    assert sim.status_code == 201
    assert sim.json()["case_number"] is not None

    dash = client.get("/api/v1/dashboard/metrics").json()
    assert dash["events_processed"] == 1
    assert dash["active_recovery_cases"] == 1


def test_disabled_by_default_no_auto_analysis(client):
    assert settings.INTELLIGENCE_ENABLED is False
    sim = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "NoIntel User",
        "customer_email": "nointel@example.com", "amount": "4999.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed", "error_description": "timeout",
    })
    case_number = sim.json()["case_number"]
    intel = client.get(f"/api/v1/recovery-cases/{case_number}/intelligence").json()
    assert intel["analyzed"] is False


# ---------------------------------------------------------------------------
# 19 & 20. Phase 1 regression via this module's fixtures
# ---------------------------------------------------------------------------
def test_phase1_simulator_still_works(client):
    res = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Legacy Flow",
        "customer_email": "legacy@example.com", "amount": "12000.00",
        "payment_method": "card", "failure_code": "GATEWAY_ERROR",
        "failure_reason": "payment_failed", "error_description": "gateway error",
    })
    assert res.status_code == 201
    assert res.json()["success"] is True
    cases = client.get("/api/v1/recovery-cases").json()
    assert cases["total"] == 1
    assert cases["items"][0]["priority"] == "HIGH"


def test_phase1_event_ingestion_still_works(db_session, sample_payment_failed_payload,
                                            sample_payment_captured_payload):
    merchant = db_session.query(Merchant).first()
    _, case1 = process_inbound_event(
        db=db_session, raw_payload=sample_payment_failed_payload, merchant_id=merchant.id
    )
    assert case1.status == "DETECTED"
    _, case2 = process_inbound_event(
        db=db_session, raw_payload=sample_payment_captured_payload, merchant_id=merchant.id
    )
    assert case2.id == case1.id
    assert case2.status == "RESOLVED"
    assert case2.amount_recovered == Decimal("8499.00")
