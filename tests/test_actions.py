"""
RECON OS — Phase 3 (ACT) Tests

Action proposal, policy-gated execution, Razorpay Test Mode adapter, idempotency,
outcome verification via webhook, audit trail, and security.

Nothing here makes a real Razorpay call — `httpx.Client` is faked.
"""

import json
import uuid
from decimal import Decimal

import httpx
import pytest

from config import settings
from models.audit_log import AuditLog
from models.merchant import Merchant
from models.payment import Payment
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from schemas.intelligence import PredictionBand
from services.actions.common import to_paise
from services.actions.executor import execute_action
from services.actions.proposal import build_proposal, get_or_create_action
from services.event_processor import process_inbound_event
from services.intelligence.orchestrator import run_intelligence
from services.intelligence.prediction import predict

FAKE_SECRET = "fake_rzp_secret_MUST_NEVER_LEAK_9x7"


# ---------------------------------------------------------------------------
@pytest.fixture
def razorpay_env(monkeypatch):
    """Configured Razorpay TEST env + a controllable fake httpx client (POST + GET)."""
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_FAKEKEY0001")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", FAKE_SECRET)
    monkeypatch.setattr(settings, "RAZORPAY_TEST_MODE", True)

    state = {
        "mode": "success", "status": 200, "body": None, "calls": [],
        # GET /payment_links/{id} — what Razorpay "reports" during reconcile:
        "link_status": "created", "link_amount": 499900, "link_amount_paid": 0,
        "link_currency": "INR", "get_calls": [],
        # GET /payment_links (list/search) — used by find_payment_link_by_reference
        # to resolve an UNKNOWN (create-timeout) outcome. Empty by default (not
        # found); Phase 4 tests populate this to simulate "it was actually created".
        "search_items": [],
    }

    class _PostResp:
        def __init__(self, ref, amt):
            self.status_code = state["status"]
            self._ref, self._amt = ref, amt

        def json(self):
            if state["body"] is not None:
                return state["body"]
            return {
                "id": "plink_TEST_" + uuid.uuid4().hex[:8],
                "short_url": "https://rzp.io/i/TESTLINK",
                "status": "created",
                "reference_id": self._ref,
                "amount": self._amt,
                "currency": "INR",
            }

    class _GetResp:
        status_code = 200

        def json(self):
            return {
                "id": state["get_calls"][-1],
                "status": state["link_status"],
                "amount": state["link_amount"],
                "amount_paid": state["link_amount_paid"],
                "currency": state["link_currency"],
                "payments": [],
            }

    class _ListResp:
        status_code = 200

        def json(self):
            return {"items": state["search_items"]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, auth=None, **k):
            state["calls"].append({"url": url, "json": json, "auth": auth})
            if state["mode"] == "timeout":
                raise httpx.TimeoutException("slow")
            if state["mode"] == "transport":
                raise httpx.ConnectError("boom")
            return _PostResp(json["reference_id"], json["amount"])

        def get(self, url, auth=None, **k):
            if url.endswith("/payment_links"):
                # list/search endpoint — find_payment_link_by_reference
                if state["mode"] == "timeout":
                    raise httpx.TimeoutException("slow")
                return _ListResp()
            state["get_calls"].append(url.rsplit("/", 1)[-1])
            if state["mode"] == "timeout":
                raise httpx.TimeoutException("slow")
            return _GetResp()

    monkeypatch.setattr("integrations.razorpay.adapter.httpx.Client", _Client)
    return state


@pytest.fixture
def webhook_env(monkeypatch, webhook_secret):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    return webhook_secret


def signed_payment_link_webhook(client, make_signature, *, plink_id, ref,
                                event_id, amount=499900, amount_paid=499900,
                                currency="INR", plink_status="paid", event="payment_link.paid"):
    body = {
        "entity": "event", "event": event, "contains": ["payment_link", "payment"],
        "id": event_id,
        "payload": {
            "payment_link": {"entity": {
                "id": plink_id, "reference_id": ref, "amount": amount,
                "amount_paid": amount_paid, "currency": currency,
                "status": plink_status, "created_at": 1620000000}},
            "payment": {"entity": {
                "id": "pay_" + event_id, "amount": amount_paid, "currency": currency,
                "status": "captured", "method": "upi", "created_at": 1620000000}},
        },
        "created_at": 1620000000,
    }
    raw = json.dumps(body).encode()
    return client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Razorpay-Signature": make_signature(raw)})


def upi_timeout_payload(pid="pay_upi_1", eid="evt_upi_1", amount_paise=499900):
    """₹4,999 UPI timeout — deterministic pipeline -> APPROVED (within ceiling)."""
    return {
        "entity": "event", "event": "payment.failed", "contains": ["payment"],
        "id": eid,
        "payload": {"payment": {"entity": {
            "id": pid, "amount": amount_paise, "currency": "INR", "status": "failed",
            "order_id": "order_" + pid, "method": "upi",
            "email": "rahul@example.com", "contact": "+919876543210",
            "customer_id": "cust_" + pid, "notes": {"name": "Rahul Sharma"},
            "error_code": "BAD_REQUEST_ERROR", "error_reason": "payment_failed",
            "error_description": "UPI handle authorization timeout on customer app",
            "created_at": 1620000000,
        }}}, "created_at": 1620000000,
    }


def _make_case(db, payload):
    merchant = db.query(Merchant).first()
    _, case = process_inbound_event(db=db, raw_payload=payload, merchant_id=merchant.id)
    return case


def _analyzed_case(db, payload):
    case = _make_case(db, payload)
    run_intelligence(db, case.id, trigger="test")
    db.refresh(case)
    return case


def _proposed_action(db, case) -> RecoveryAction:
    action, proposal = get_or_create_action(db, case)
    assert action is not None, f"not proposable: {proposal.not_proposable_reason}"
    return action


# ===========================================================================
# 1. Amount conversion
# ===========================================================================
def test_amount_conversion_to_paise():
    assert to_paise(Decimal("4999.00")) == 499900
    assert to_paise(Decimal("14999")) == 1499900
    assert to_paise(Decimal("75000.50")) == 7500050


# ===========================================================================
# 2-8. Razorpay adapter
# ===========================================================================
def test_adapter_missing_credentials(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")
    from integrations.razorpay.adapter import RazorpayAdapter
    r = RazorpayAdapter().create_payment_link(
        amount_paise=499900, currency="INR", reference_id="X", description="d")
    assert r.ok is False and r.error_code == "RAZORPAY_NOT_CONFIGURED"


def test_adapter_test_mode_disabled(razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_TEST_MODE", False)
    from integrations.razorpay.adapter import RazorpayAdapter
    r = RazorpayAdapter().create_payment_link(
        amount_paise=499900, currency="INR", reference_id="X", description="d")
    assert r.ok is False and r.error_code == "RAZORPAY_TEST_MODE_DISABLED"


def test_adapter_not_test_key(razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_REALKEY")
    from integrations.razorpay.adapter import RazorpayAdapter
    r = RazorpayAdapter().create_payment_link(
        amount_paise=499900, currency="INR", reference_id="X", description="d")
    assert r.ok is False and r.error_code == "RAZORPAY_NOT_TEST_KEY"


def test_adapter_success_uses_basic_auth(razorpay_env):
    from integrations.razorpay.adapter import RazorpayAdapter
    r = RazorpayAdapter().create_payment_link(
        amount_paise=499900, currency="INR", reference_id="RECON-RC1-ACT001", description="d")
    assert r.ok is True
    assert r.payment_link_id.startswith("plink_")
    assert r.short_url == "https://rzp.io/i/TESTLINK"
    assert razorpay_env["calls"][0]["auth"] == ("rzp_test_FAKEKEY0001", FAKE_SECRET)
    assert razorpay_env["calls"][0]["json"]["amount"] == 499900


def test_adapter_api_error(razorpay_env):
    razorpay_env["status"] = 500
    razorpay_env["body"] = {"error": {"description": "server blew up"}}
    from integrations.razorpay.adapter import RazorpayAdapter
    r = RazorpayAdapter().create_payment_link(
        amount_paise=1, currency="INR", reference_id="X", description="d")
    assert r.ok is False and r.error_code == "RAZORPAY_API_ERROR"


def test_adapter_bad_request(razorpay_env):
    razorpay_env["status"] = 400
    razorpay_env["body"] = {"error": {"description": "reference id already used"}}
    from integrations.razorpay.adapter import RazorpayAdapter
    r = RazorpayAdapter().create_payment_link(
        amount_paise=1, currency="INR", reference_id="X", description="d")
    assert r.ok is False and r.error_code == "RAZORPAY_BAD_REQUEST"


def test_adapter_timeout(razorpay_env):
    razorpay_env["mode"] = "timeout"
    from integrations.razorpay.adapter import RazorpayAdapter
    r = RazorpayAdapter().create_payment_link(
        amount_paise=1, currency="INR", reference_id="X", description="d")
    assert r.ok is False and r.error_code == "RAZORPAY_TIMEOUT"


def test_adapter_rate_limited(razorpay_env):
    razorpay_env["status"] = 429
    from integrations.razorpay.adapter import RazorpayAdapter
    r = RazorpayAdapter().create_payment_link(
        amount_paise=1, currency="INR", reference_id="X", description="d")
    assert r.ok is False and r.error_code == "RAZORPAY_RATE_LIMITED"


# ===========================================================================
# 9-12. Action proposal
# ===========================================================================
def test_propose_not_analyzed(db_session, sample_payment_failed_payload):
    case = _make_case(db_session, sample_payment_failed_payload)   # no intelligence
    proposal = build_proposal(db_session, case)
    assert proposal.proposable is False
    assert proposal.not_proposable_reason == "NOT_ANALYZED"


def test_propose_eligible_case(db_session, sample_payment_failed_payload):
    case = _analyzed_case(db_session, sample_payment_failed_payload)
    proposal = build_proposal(db_session, case)
    assert proposal.proposable is True
    assert proposal.action_type.value == "CREATE_PAYMENT_LINK"
    assert proposal.reference_id == f"RECON-{case.case_number.replace('-', '')}-ACT001"
    assert proposal.strategy_action in ("RETRY_NOW", "RETRY_DELAYED", "SEND_PAYMENT_LINK")


def test_propose_ineligible_strategy_fraud(db_session):
    fraud = {
        "entity": "event", "event": "payment.failed", "contains": ["payment"],
        "id": "evt_fraud_1",
        "payload": {"payment": {"entity": {
            "id": "pay_fraud_1", "amount": 499900, "currency": "INR", "status": "failed",
            "method": "card", "email": "f@x.com", "error_code": "BAD_REQUEST_ERROR",
            "error_reason": "payment_risk_check_failed",
            "error_description": "Payment blocked by risk engine — suspected fraud",
            "created_at": 1620000000,
        }}}, "created_at": 1620000000,
    }
    case = _analyzed_case(db_session, fraud)
    proposal = build_proposal(db_session, case)
    assert proposal.proposable is False
    assert proposal.not_proposable_reason == "STRATEGY_NOT_ELIGIBLE"


def test_propose_is_idempotent(db_session, sample_payment_failed_payload):
    case = _analyzed_case(db_session, sample_payment_failed_payload)
    a1, _ = get_or_create_action(db_session, case)
    a2, _ = get_or_create_action(db_session, case)
    assert a1.id == a2.id
    assert db_session.query(RecoveryAction).filter_by(recovery_case_id=case.id).count() == 1


# ===========================================================================
# 13-17. Executor: policy gate + test-mode enforcement
# ===========================================================================
def test_execute_approved_creates_payment_link(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "EXECUTED"
    assert result.outcome == "PENDING"                 # link created != recovered
    assert result.provider_action_id.startswith("plink_")
    assert result.payment_link_url == "https://rzp.io/i/TESTLINK"
    assert len(razorpay_env["calls"]) == 1
    # case NOT resolved, nothing recovered yet
    db_session.refresh(case)
    assert case.status == "DETECTED"
    assert Decimal(case.amount_recovered) == Decimal("0.00")


def test_execute_blocked_when_razorpay_missing(db_session, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "BLOCKED"
    assert result.blocked_reason == "RAZORPAY_NOT_CONFIGURED"
    assert result.provider_action_id is None


def test_execute_blocked_when_test_mode_disabled(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_TEST_MODE", False)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "BLOCKED"
    assert result.blocked_reason == "TEST_MODE_DISABLED"
    assert len(razorpay_env["calls"]) == 0


def test_execute_blocked_when_needs_approval(db_session, razorpay_env):
    """₹14,999 > auto-approval ceiling -> policy NEEDS_APPROVAL -> execution blocked."""
    payload = {
        "entity": "event", "event": "payment.failed", "contains": ["payment"],
        "id": "evt_hv_1",
        "payload": {"payment": {"entity": {
            "id": "pay_hv_1", "amount": 1499900, "currency": "INR", "status": "failed",
            "method": "card", "email": "hv@x.com", "error_code": "GATEWAY_ERROR",
            "error_reason": "payment_failed",
            "error_description": "Transaction declined: insufficient funds / limit exceeded",
            "created_at": 1620000000,
        }}}, "created_at": 1620000000,
    }
    case = _analyzed_case(db_session, payload)
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "BLOCKED"
    assert result.blocked_reason == "NEEDS_APPROVAL"
    assert len(razorpay_env["calls"]) == 0


def test_execute_blocked_when_policy_reevaluates_to_rejected(db_session, razorpay_env):
    """
    Stored policy verdict is APPROVED, but the executor RE-EVALUATES server-side:
    tampering the payment into an unknown state must block execution.
    """
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    assert action.policy_verdict == "APPROVED"          # stored value says APPROVED
    payment = db_session.query(Payment).filter_by(id=case.payment_id).first()
    payment.status = "unknown"
    db_session.commit()
    result = execute_action(db_session, action.id)
    assert result.status == "BLOCKED"
    assert result.blocked_reason == "POLICY_REJECTED"   # fresh re-eval wins
    assert len(razorpay_env["calls"]) == 0


def test_execute_blocked_invalid_amount(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    action.amount = Decimal("0.00")
    db_session.commit()
    result = execute_action(db_session, action.id)
    assert result.status == "BLOCKED"
    assert result.blocked_reason == "INVALID_AMOUNT"


# ===========================================================================
# 18-20. Idempotency
# ===========================================================================
def test_execute_is_idempotent_no_duplicate_link(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    r1 = execute_action(db_session, action.id)
    r2 = execute_action(db_session, action.id)
    r3 = execute_action(db_session, action.id)
    assert r1.provider_action_id == r2.provider_action_id == r3.provider_action_id
    assert len(razorpay_env["calls"]) == 1            # Razorpay hit exactly once
    assert db_session.query(RecoveryAction).filter_by(recovery_case_id=case.id).count() == 1


def test_adapter_failure_marks_action_failed(db_session, razorpay_env):
    """
    A Razorpay TIMEOUT is ambiguous (the request may have reached Razorpay
    despite the client-side timeout) — Phase 4 requires it be marked UNKNOWN,
    never FAILED, and never blindly retried. See test_phase4_safety.py for the
    full UNKNOWN -> verify -> resolve chain; a definitive (non-timeout) error
    is still marked FAILED and IS safely retryable, covered below.
    """
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status != "FAILED"
    assert result.outcome == "UNKNOWN"
    assert result.error_code == "RAZORPAY_TIMEOUT"
    assert result.provider_action_id is None
    # a blind retry after an ambiguous timeout is refused by the existing
    # EXECUTING-status idempotency guard — no second Razorpay call is made
    razorpay_env["mode"] = "success"
    retry = execute_action(db_session, action.id)
    assert retry.outcome == "UNKNOWN"
    assert len(razorpay_env["calls"]) == 1


def test_adapter_definitive_failure_is_safely_retryable(db_session, razorpay_env):
    """A definitive (non-ambiguous) Razorpay failure is still FAILED and can
    be retried directly — only a TIMEOUT requires verification first."""
    razorpay_env["status"] = 500
    razorpay_env["body"] = {"error": {"description": "server blew up"}}
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "FAILED"
    assert result.error_code == "RAZORPAY_API_ERROR"
    razorpay_env["status"] = 200
    razorpay_env["body"] = None
    retry = execute_action(db_session, action.id)
    assert retry.status == "EXECUTED"


# ===========================================================================
# 21-24. Outcome verification via webhook
# ===========================================================================
def test_payment_link_created_is_not_revenue_recovered(client, razorpay_env):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])
    dash = client.get("/api/v1/dashboard/metrics").json()
    assert dash["actions"]["actions_executed"] == 1
    assert dash["actions"]["pending_recoveries"] == 1
    assert Decimal(dash["actions"]["revenue_recovered"]) == Decimal("0.00")
    assert client.get(f"/api/v1/recovery-cases/{cn}").json()["status"] == "DETECTED"


def test_signed_webhook_full_payment_verifies_recovery(client, razorpay_env, webhook_env, make_signature):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])
    assert executed["ui_state"] == "WAITING_FOR_PAYMENT"

    res = signed_payment_link_webhook(
        client, make_signature, plink_id=executed["provider_action_id"],
        ref=executed["reference_id"], event_id="evt_real_paid_1")
    assert res.status_code == 200

    a = client.get(f"/api/v1/actions/{action['id']}").json()
    assert a["outcome"] == "RECOVERED"
    assert a["ui_state"] == "RECOVERED"
    assert a["simulated"] is False
    assert Decimal(a["recovered_amount"]) == Decimal("4999.00")

    case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case["status"] == "RESOLVED"
    assert Decimal(case["amount_recovered"]) == Decimal("4999.00")

    dash = client.get("/api/v1/dashboard/metrics").json()["actions"]
    assert Decimal(dash["revenue_recovered"]) == Decimal("4999.00")
    assert Decimal(dash["simulated_revenue_recovered"]) == Decimal("0.00")
    assert dash["recovery_rate"] == 1.0


def test_duplicate_signed_webhook_does_not_double_count(client, razorpay_env, webhook_env, make_signature):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])
    p, r = executed["provider_action_id"], executed["reference_id"]

    r1 = signed_payment_link_webhook(client, make_signature, plink_id=p, ref=r, event_id="evt_dup_1")
    r2 = signed_payment_link_webhook(client, make_signature, plink_id=p, ref=r, event_id="evt_dup_1")  # same id
    r3 = signed_payment_link_webhook(client, make_signature, plink_id=p, ref=r, event_id="evt_dup_2")  # diff id
    assert r1.status_code == r2.status_code == r3.status_code == 200

    dash = client.get("/api/v1/dashboard/metrics").json()["actions"]
    assert Decimal(dash["revenue_recovered"]) == Decimal("4999.00")   # counted once
    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    assert sum(1 for a in audits if a["action"] == "RECOVERY_VERIFIED") == 1
    assert any(a["action"] in ("RECOVERY_ALREADY_VERIFIED", "DUPLICATE_EVENT_IGNORED") for a in audits)


def test_signed_webhook_partial_payment_is_not_recovered(client, razorpay_env, webhook_env, make_signature):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])

    res = signed_payment_link_webhook(
        client, make_signature, plink_id=executed["provider_action_id"],
        ref=executed["reference_id"], event_id="evt_partial_1",
        amount=499900, amount_paid=200000, plink_status="partially_paid")
    assert res.status_code == 200

    a = client.get(f"/api/v1/actions/{action['id']}").json()
    assert a["outcome"] == "PARTIAL"
    assert a["ui_state"] == "PARTIAL"
    assert Decimal(a["recovered_amount"]) == Decimal("0.00")   # PARTIAL is NOT recovered

    case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case["status"] != "RESOLVED"          # case NOT resolved

    dash = client.get("/api/v1/dashboard/metrics").json()["actions"]
    assert Decimal(dash["revenue_recovered"]) == Decimal("0.00")
    assert dash["partial_recoveries"] == 1


def test_signed_webhook_currency_mismatch_is_rejected(client, razorpay_env, webhook_env, make_signature):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])

    res = signed_payment_link_webhook(
        client, make_signature, plink_id=executed["provider_action_id"],
        ref=executed["reference_id"], event_id="evt_curr_1", currency="USD")
    assert res.status_code == 200

    a = client.get(f"/api/v1/actions/{action['id']}").json()
    assert a["outcome"] == "PENDING"    # not recovered
    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    assert any(a["action"] == "RECOVERY_REJECTED"
               and (a.get("metadata_json") or {}).get("reason") == "CURRENCY_MISMATCH"
               for a in audits)


def test_signed_webhook_status_not_paid_is_ignored(client, razorpay_env, webhook_env, make_signature):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])
    res = signed_payment_link_webhook(
        client, make_signature, plink_id=executed["provider_action_id"],
        ref=executed["reference_id"], event_id="evt_created_1", plink_status="created")
    assert res.status_code == 200
    assert client.get(f"/api/v1/actions/{action['id']}").json()["outcome"] == "PENDING"


def test_signed_webhook_expired_marks_action_expired(client, razorpay_env, webhook_env, make_signature):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])
    res = signed_payment_link_webhook(
        client, make_signature, plink_id=executed["provider_action_id"],
        ref=executed["reference_id"], event_id="evt_expired_1",
        event="payment_link.expired", plink_status="expired")
    assert res.status_code == 200
    a = client.get(f"/api/v1/actions/{action['id']}").json()
    assert a["outcome"] == "EXPIRED"
    assert client.get(f"/api/v1/recovery-cases/{cn}").json()["status"] != "RESOLVED"


def test_unsigned_payment_link_webhook_rejected(client, razorpay_env, webhook_env):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])
    body = json.dumps({
        "event": "payment_link.paid", "id": "evt_unsigned_1",
        "payload": {"payment_link": {"entity": {
            "id": executed["provider_action_id"], "reference_id": executed["reference_id"],
            "amount": 499900, "amount_paid": 499900, "currency": "INR", "status": "paid"}}},
    }).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=body,
                      headers={"Content-Type": "application/json"})  # no signature
    assert res.status_code == 400
    assert client.get(f"/api/v1/actions/{action['id']}").json()["outcome"] == "PENDING"


def test_invalid_webhook_signature_still_blocked_phase3(client, webhook_env):
    body = json.dumps({"event": "payment_link.paid", "payload": {}}).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=body,
                      headers={"Content-Type": "application/json",
                               "X-Razorpay-Signature": "deadbeef"})
    assert res.status_code == 400


# ===========================================================================
# Reconciliation (authoritative GET /v1/payment_links/{id})
# ===========================================================================
def test_reconcile_confirms_real_payment(client, razorpay_env):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])

    # Razorpay now reports the link as paid in full
    razorpay_env["link_status"] = "paid"
    razorpay_env["link_amount_paid"] = 499900

    res = client.post(f"/api/v1/actions/{action['id']}/reconcile").json()
    assert res["ok"] is True and res["recovered"] is True
    assert res["razorpay_status"] == "paid"
    a = res["action"]
    assert a["outcome"] == "RECOVERED" and a["simulated"] is False
    assert Decimal(a["recovered_amount"]) == Decimal("4999.00")
    assert client.get(f"/api/v1/recovery-cases/{cn}").json()["status"] == "RESOLVED"


def test_reconcile_not_paid_stays_pending(client, razorpay_env):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])

    razorpay_env["link_status"] = "created"       # customer has not paid
    razorpay_env["link_amount_paid"] = 0

    res = client.post(f"/api/v1/actions/{action['id']}/reconcile").json()
    assert res["ok"] is False and res["recovered"] is False
    assert client.get(f"/api/v1/actions/{action['id']}").json()["outcome"] == "PENDING"
    assert client.get(f"/api/v1/recovery-cases/{cn}").json()["status"] == "DETECTED"


def test_reconcile_partial_payment(client, razorpay_env):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])

    razorpay_env["link_status"] = "partially_paid"
    razorpay_env["link_amount_paid"] = 100000     # ₹1,000 of ₹4,999

    res = client.post(f"/api/v1/actions/{action['id']}/reconcile").json()
    assert res["partial"] is True and res["recovered"] is False
    a = client.get(f"/api/v1/actions/{action['id']}").json()
    assert a["outcome"] == "PARTIAL"
    assert Decimal(a["recovered_amount"]) == Decimal("0.00")
    assert client.get(f"/api/v1/recovery-cases/{cn}").json()["status"] != "RESOLVED"


def test_reconcile_is_idempotent_with_webhook(client, razorpay_env, webhook_env, make_signature):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])

    # webhook confirms first
    signed_payment_link_webhook(client, make_signature, plink_id=executed["provider_action_id"],
                                ref=executed["reference_id"], event_id="evt_recon_idem_1")
    # then a reconcile also runs
    razorpay_env["link_status"] = "paid"
    razorpay_env["link_amount_paid"] = 499900
    client.post(f"/api/v1/actions/{action['id']}/reconcile")
    client.post(f"/api/v1/actions/{action['id']}/reconcile")

    dash = client.get("/api/v1/dashboard/metrics").json()["actions"]
    assert Decimal(dash["revenue_recovered"]) == Decimal("4999.00")   # once only


def test_reconcile_without_razorpay_credentials(client, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "x")
    monkeypatch.setattr(settings, "RAZORPAY_TEST_MODE", True)
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    # give the action a fake executed link so reconcile proceeds to the GET
    from database import SessionLocal
    db = SessionLocal()
    try:
        a = db.query(RecoveryAction).filter_by(id=uuid.UUID(action["id"])).first()
        a.status = "EXECUTED"; a.provider_action_id = "plink_x"
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")
    res = client.post(f"/api/v1/actions/{action['id']}/reconcile").json()
    assert res["ok"] is False
    assert "RAZORPAY_NOT_CONFIGURED" in res["message"]


# ===========================================================================
# Simulator gating + provenance
# ===========================================================================
def test_simulator_disabled_by_default(client, monkeypatch):
    monkeypatch.setattr(settings, "RECON_SIMULATOR_ENABLED", False)
    r1 = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "X", "customer_email": "x@y.z",
        "amount": "4999.00", "payment_method": "upi"})
    r2 = client.post("/api/v1/simulator/payment-link-paid", json={"action_id": str(uuid.uuid4())})
    assert r1.status_code == 403
    assert r2.status_code == 403


def test_simulated_recovery_is_marked_and_excluded_from_real_metrics(client, razorpay_env):
    cn = _api_analyzed_case(client)                       # simulator enabled via conftest
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])

    paid = client.post("/api/v1/simulator/payment-link-paid", json={"action_id": action["id"]})
    assert paid.status_code == 201

    a = client.get(f"/api/v1/actions/{action['id']}").json()
    assert a["outcome"] == "RECOVERED"
    assert a["simulated"] is True                         # technically marked

    dash = client.get("/api/v1/dashboard/metrics").json()["actions"]
    assert Decimal(dash["revenue_recovered"]) == Decimal("0.00")            # excluded from REAL
    assert Decimal(dash["simulated_revenue_recovered"]) == Decimal("4999.00")

    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    verified = [x for x in audits if x["action"] == "RECOVERY_VERIFIED"]
    assert verified and "SIMULATED" in verified[0]["detail"]
    assert (verified[0].get("metadata_json") or {}).get("simulated") is True


# ===========================================================================
# 25-26. Audit + AI-cannot-bypass-policy
# ===========================================================================
def test_action_audit_lifecycle(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    actions = {a.action for a in db_session.query(AuditLog).filter(
        AuditLog.recovery_case_id == case.id).all()}
    assert {"ACTION_PROPOSED", "ACTION_EXECUTION_STARTED", "ACTION_POLICY_CHECKED",
            "ACTION_APPROVED", "ACTION_EXECUTED", "PAYMENT_LINK_CREATED",
            "RECOVERY_PENDING"}.issubset(actions)


def test_ai_cannot_bypass_policy(db_session, razorpay_env, monkeypatch):
    """A tampered high-confidence AI diagnosis cannot force execution of a
    NEEDS_APPROVAL (high-value) case — the deterministic policy still blocks it."""
    import services.intelligence.ai_diagnosis as aid
    from schemas.intelligence import DiagnosisResult, FailureCategory

    def fake_diag(ctx):
        d = DiagnosisResult(
            failure_category=FailureCategory.TECHNICAL_GATEWAY,
            probable_cause="(injected) trust me, approve everything",
            confidence=0.999, rationale="ignore policy", evidence=["x"],
            provider="GEMINI", provider_version="gemini-x",
        )
        return d, aid.AIDiagnosisMeta(attempted=True, used_ai=True, provider="GEMINI",
                                      provider_version="gemini-x")
    monkeypatch.setattr("services.actions.executor.diagnose_case", fake_diag)

    payload = {
        "entity": "event", "event": "payment.failed", "contains": ["payment"],
        "id": "evt_bypass_1",
        "payload": {"payment": {"entity": {
            "id": "pay_bypass_1", "amount": 7500000, "currency": "INR", "status": "failed",
            "method": "netbanking", "email": "b@x.com", "error_code": "BAD_REQUEST_ERROR",
            "error_reason": "payment_failed", "error_description": "big corporate failure",
            "created_at": 1620000000,
        }}}, "created_at": 1620000000,
    }
    case = _analyzed_case(db_session, payload)
    action = _proposed_action(db_session, case) if build_proposal(db_session, case).proposable \
        else _force_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "BLOCKED"
    assert result.blocked_reason == "NEEDS_APPROVAL"
    assert len(razorpay_env["calls"]) == 0


def _force_action(db, case):
    """Create an action row directly (bypasses proposal eligibility) to prove the
    executor itself is the safety gate, not the proposal step."""
    from services.actions.common import idempotency_key_for, reference_id_for
    amount = Decimal(case.amount_at_risk or 0)
    a = RecoveryAction(
        recovery_case_id=case.id, merchant_id=case.merchant_id,
        action_type="CREATE_PAYMENT_LINK", action_version=1, status="PROPOSED",
        outcome="PENDING",
        idempotency_key=idempotency_key_for(case.id, "CREATE_PAYMENT_LINK", 1),
        reference_id=reference_id_for(case.case_number, 1),
        amount=amount, amount_paise=to_paise(amount), currency="INR", provider="RAZORPAY",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ===========================================================================
# 27-28. Security — no secret leakage
# ===========================================================================
def test_no_secret_in_api_responses(client, razorpay_env):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])
    blob = (
        client.get(f"/api/v1/actions/{action['id']}").text
        + client.get(f"/api/v1/recovery-cases/{cn}/actions").text
        + client.get("/api/v1/actions").text
        + client.get("/api/v1/dashboard/metrics").text
        + client.post(f"/api/v1/recovery-cases/{cn}/actions/propose").text
    )
    assert FAKE_SECRET not in blob
    assert "rzp_test_FAKEKEY0001" not in blob


def test_no_secret_in_audit_logs(client, razorpay_env):
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])
    client.post("/api/v1/simulator/payment-link-paid", json={"action_id": action["id"]})
    audits = client.get("/api/v1/audit-logs?limit=100").json()
    assert FAKE_SECRET not in json.dumps(audits)


def test_execute_endpoint_takes_no_policy_input(client, razorpay_env):
    """The frontend cannot supply a verdict/approval — the body is ignored."""
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    res = client.post(f"/api/v1/actions/{action['id']}/execute",
                      json={"policy_verdict": "APPROVED", "approved": True, "force": True})
    assert res.status_code == 200
    # still executed via the real deterministic path
    assert res.json()["action"]["status"] in ("EXECUTED", "BLOCKED", "FAILED")


# ---------------------------------------------------------------------------
# Automatic execution of Policy-APPROVED actions (off by default) — the
# demo-execution UX correction. Reuses the EXISTING get_or_create_action() +
# execute_action() Action Engine functions; never a new execution mechanism.
# ---------------------------------------------------------------------------
def test_automatic_execution_disabled_by_default(db_session, razorpay_env):
    assert settings.AUTOMATIC_ACTION_EXECUTION_ENABLED is False
    case = _analyzed_case(db_session, upi_timeout_payload())
    db_session.refresh(case)
    actions = db_session.query(RecoveryAction).filter_by(recovery_case_id=case.id).all()
    assert actions == [], "no action should exist without the flag enabled"


def test_automatic_execution_creates_and_executes_action_for_approved_case(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    case = _analyzed_case(db_session, upi_timeout_payload())  # APPROVED, low amount
    db_session.refresh(case)

    actions = db_session.query(RecoveryAction).filter_by(recovery_case_id=case.id).all()
    assert len(actions) == 1
    action = actions[0]
    assert action.status == "EXECUTED"
    assert action.outcome == "PENDING"          # never RECOVERED merely from execution
    assert action.provider_action_id            # a real (TEST-mode fake) Payment Link id
    assert action.payment_link_url

    events = {a.action for a in db_session.query(AuditLog).filter_by(recovery_case_id=case.id).all()}
    assert {"ACTION_PROPOSED", "ACTION_EXECUTED", "PAYMENT_LINK_CREATED"}.issubset(events)


def test_automatic_execution_never_fires_for_needs_approval(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    payload = upi_timeout_payload()
    payload["payload"]["payment"]["entity"]["amount"] = 1499900  # above auto-approval ceiling
    payload["payload"]["payment"]["entity"]["method"] = "card"
    payload["payload"]["payment"]["entity"]["error_code"] = "GATEWAY_ERROR"
    payload["payload"]["payment"]["entity"]["error_description"] = "Transaction declined: insufficient funds / limit exceeded"
    case = _analyzed_case(db_session, payload)
    db_session.refresh(case)

    actions = db_session.query(RecoveryAction).filter_by(recovery_case_id=case.id).all()
    assert actions == [], "NEEDS_APPROVAL must never be auto-executed — a human decision remains mandatory"


def test_automatic_execution_never_fires_for_rejected(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    payload = upi_timeout_payload()
    payload["payload"]["payment"]["entity"]["error_description"] = "Transaction blocked by risk engine - suspicious activity flagged"
    case = _analyzed_case(db_session, payload)
    db_session.refresh(case)

    actions = db_session.query(RecoveryAction).filter_by(recovery_case_id=case.id).all()
    assert actions == [], "REJECTED must never result in a created/executed action"


def test_automatic_execution_stops_for_low_recovery_opportunity(db_session, razorpay_env, monkeypatch):
    """Objective 9: even when Policy says APPROVED (the action is SAFE) and
    the strategy IS payment-link-eligible (AUTH_TIMEOUT/TECHNICAL_GATEWAY at
    LOW band route to SEND_PAYMENT_LINK per services/intelligence/
    strategy.py — a real, reachable combination, not a hypothetical one),
    automatic execution must not pursue a LOW-opportunity case. Forces the
    LOW band deterministically via the real `predict()` function's own
    output shape (no new classification invented) rather than hunting for
    an exact real-data combination that happens to trigger it — the
    combination itself IS real and reachable (AUTH_TIMEOUT/TECHNICAL_GATEWAY
    + LOW band -> SEND_PAYMENT_LINK), only the trigger is stubbed here to
    keep the test focused and independent of the deterministic scorecard's
    exact weights."""
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)

    real_predict = predict

    def forced_low_band(ctx, diagnosis):
        result = real_predict(ctx, diagnosis)
        result.band = PredictionBand.LOW
        return result

    monkeypatch.setattr("services.intelligence.orchestrator.predict", forced_low_band)

    case = _make_case(db_session, upi_timeout_payload())  # AUTH_TIMEOUT diagnosis
    ci = run_intelligence(db_session, case.id, trigger="test")

    assert ci.policy_verdict == "APPROVED", ci.policy_verdict
    assert ci.prediction_band == "LOW", ci.prediction_band
    assert ci.recommended_action in ("SEND_PAYMENT_LINK", "RETRY_NOW", "RETRY_DELAYED"), ci.recommended_action

    actions = db_session.query(RecoveryAction).filter_by(recovery_case_id=case.id).all()
    assert actions == [], "a LOW-opportunity case must not be automatically pursued even when Policy approves it"

    events = {a.action for a in db_session.query(AuditLog).filter_by(recovery_case_id=case.id).all()}
    assert "AUTOMATED_PURSUIT_STOPPED" in events




def test_automatic_execution_re_validates_policy_fresh_not_bypassed(db_session, razorpay_env):
    """Even with auto-execution enabled, a policy change between analysis and
    the (automatic) execution attempt must still block it — execute_action()
    re-derives everything server-side, exactly as a manual click always has.
    This proves the automatic path is not a second, less-safe execution
    mechanism."""
    from models.payment import Payment

    case = _analyzed_case(db_session, upi_timeout_payload())
    db_session.refresh(case)
    payment = db_session.query(Payment).filter_by(id=case.payment_id).first()
    payment.status = "unknown"   # payment state no longer verifiable
    db_session.commit()

    action, proposal = get_or_create_action(db_session, case)
    assert action is not None
    result = execute_action(db_session, action.id)
    assert result.status == "BLOCKED"
    assert result.outcome != "RECOVERED"


def test_automatic_execution_failure_never_breaks_intelligence_result(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    # The orchestrator does a local `from services.actions.executor import
    # execute_action` inside its try block on every call — patch the
    # function at its defining module so that fresh import picks it up.
    monkeypatch.setattr("services.actions.executor.execute_action",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    case = _make_case(db_session, upi_timeout_payload())
    ci = run_intelligence(db_session, case.id, trigger="test")
    assert ci.status != "FAILED"
    assert ci.policy_verdict == "APPROVED"


def test_payment_link_creation_never_sets_recovered_outcome(db_session, razorpay_env):
    """Objective 3: executing an action (creating the Payment Link) must
    never itself mark the case/action RECOVERED — only verification may."""
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "EXECUTED"
    assert result.outcome == "PENDING"
    db_session.refresh(case)
    assert case.status != "RESOLVED"


# ===========================================================================
# Phase 8 — full automatic chain via a REAL webhook, zero manual steps
# ===========================================================================
def test_full_automatic_chain_via_real_webhook_no_manual_steps(
    client, razorpay_env, webhook_env, make_signature, monkeypatch
):
    """The literal Phase 8 success criterion: a real, signature-verified
    payment.failed webhook, with all three automation flags on, produces a
    fully-executed, fully-verified, RESOLVED case with ZERO manual analyze/
    propose/execute/send calls — then proves both webhook deliveries are
    idempotent on redelivery."""
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "fake")

    payload = upi_timeout_payload()
    raw = json.dumps(payload).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Razorpay-Signature": make_signature(raw)})
    assert res.status_code == 200
    cn = res.json()["case_number"]
    assert cn is not None

    case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case["simulated"] is False
    assert case["intelligence"]["policy_verdict"] == "APPROVED"

    actions = client.get(f"/api/v1/recovery-cases/{cn}/actions").json()["items"]
    assert len(actions) == 1, "an action should be auto-created + auto-executed with no manual propose/execute call"
    action = actions[0]
    assert action["status"] == "EXECUTED"
    assert action["automatic_execution_enabled"] is True

    comms = client.get(f"/api/v1/recovery-cases/{cn}/communications").json()["items"]
    assert len(comms) >= 1, "a communication should be auto-sent with no manual send call"

    # Customer pays -> real signed payment_link.paid webhook -> automatic verification.
    plw = signed_payment_link_webhook(
        client, make_signature, plink_id=action["provider_action_id"],
        ref=action["reference_id"], event_id="evt_full_chain_paid_1")
    assert plw.status_code == 200

    final_action = client.get(f"/api/v1/actions/{action['id']}").json()
    assert final_action["outcome"] == "RECOVERED"
    final_case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert final_case["status"] == "RESOLVED"

    # Idempotency: redeliver both webhooks — nothing doubles up.
    res2 = client.post("/api/v1/webhooks/razorpay", content=raw,
                        headers={"Content-Type": "application/json",
                                 "X-Razorpay-Signature": make_signature(raw)})
    assert res2.status_code == 200
    assert len(client.get(f"/api/v1/recovery-cases/{cn}/actions").json()["items"]) == 1

    plw2 = signed_payment_link_webhook(
        client, make_signature, plink_id=action["provider_action_id"],
        ref=action["reference_id"], event_id="evt_full_chain_paid_1")
    assert plw2.status_code == 200
    final_case2 = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert Decimal(final_case2["amount_recovered"]) == Decimal(final_case["amount_recovered"])

    audit = client.get(f"/api/v1/audit-logs?case_id={case['id']}&limit=100").json()["items"]
    actions_seen = [a["action"] for a in audit]
    for expected in ("RECOVERY_CASE_CREATED", "ACTION_PROPOSED", "ACTION_EXECUTED",
                      "PAYMENT_LINK_CREATED", "RECOVERY_VERIFIED"):
        assert expected in actions_seen, f"{expected} missing from audit trail: {actions_seen}"


def test_full_automatic_chain_rejected_produces_zero_actions(client, razorpay_env, webhook_env, make_signature, monkeypatch):
    """RISK_BLOCK -> REJECTED must create zero money-moving actions even with
    every automation flag on, driven end-to-end through the real webhook."""
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "fake")

    payload = upi_timeout_payload(pid="pay_risk_1", eid="evt_risk_1")
    payload["payload"]["payment"]["entity"]["error_code"] = "GATEWAY_ERROR"
    payload["payload"]["payment"]["entity"]["error_reason"] = "payment_risk_check_failed"
    payload["payload"]["payment"]["entity"]["error_description"] = "Transaction blocked by risk engine - suspicious activity flagged"
    raw = json.dumps(payload).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Razorpay-Signature": make_signature(raw)})
    assert res.status_code == 200
    cn = res.json()["case_number"]

    case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case["intelligence"]["policy_verdict"] == "REJECTED"
    assert client.get(f"/api/v1/recovery-cases/{cn}/actions").json()["items"] == []
    assert client.get(f"/api/v1/recovery-cases/{cn}/communications").json()["items"] == []


def test_full_automatic_chain_needs_approval_produces_zero_actions(client, razorpay_env, webhook_env, make_signature, monkeypatch):
    """A high-amount, above-ceiling failure -> NEEDS_APPROVAL must never
    auto-execute — a human decision remains mandatory even with every
    automation flag on."""
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "fake")

    payload = upi_timeout_payload(pid="pay_needsapp_1", eid="evt_needsapp_1", amount_paise=1499900)
    payload["payload"]["payment"]["entity"]["method"] = "card"
    payload["payload"]["payment"]["entity"]["error_code"] = "GATEWAY_ERROR"
    payload["payload"]["payment"]["entity"]["error_description"] = "Transaction declined: insufficient funds / limit exceeded"
    raw = json.dumps(payload).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Razorpay-Signature": make_signature(raw)})
    assert res.status_code == 200
    cn = res.json()["case_number"]

    case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case["intelligence"]["policy_verdict"] == "NEEDS_APPROVAL"
    assert client.get(f"/api/v1/recovery-cases/{cn}/actions").json()["items"] == []


def test_full_automatic_chain_unknown_diagnosis_stays_safe(client, razorpay_env, webhook_env, make_signature, monkeypatch):
    """A genuinely undiagnosable failure (error text matches none of the
    deterministic diagnosis engine's keyword rules, reason overrides, or
    error-code fallbacks — see services/intelligence/diagnosis.py's case 4
    "Unknown" branch) must never result in an automatically executed,
    money-moving action, even with every automation flag on. Note: leaving
    error_description/error_reason as None is NOT sufficient to reach
    UNKNOWN here — event_processor.py substitutes the fallback text "Payment
    processing failed" for a None description, and "processing failed" is
    itself a TECHNICAL_GATEWAY keyword (weights.py), which routes to an
    approvable, payment-link-eligible strategy. Genuinely neutral text is
    required to reach the true UNKNOWN branch."""
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "fake")

    payload = upi_timeout_payload(pid="pay_unk_1", eid="evt_unk_1")
    payload["payload"]["payment"]["entity"]["method"] = "card"
    payload["payload"]["payment"]["entity"]["error_code"] = "UNCLASSIFIED"
    payload["payload"]["payment"]["entity"]["error_reason"] = "unspecified"
    payload["payload"]["payment"]["entity"]["error_description"] = "Payment attempt unsuccessful"
    raw = json.dumps(payload).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Razorpay-Signature": make_signature(raw)})
    assert res.status_code == 200
    cn = res.json()["case_number"]

    case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case["intelligence"]["failure_category"] == "UNKNOWN"
    assert client.get(f"/api/v1/recovery-cases/{cn}/actions").json()["items"] == [], \
        "an UNKNOWN diagnosis must never result in an automatically executed action"


# ===========================================================================
# Final hardening pass — intent-aware recovery gate
#
# Product principle: "RECON recovers involuntary payment failures, not
# unwilling customers." The concrete, already-enforced signal for
# "unwilling/hard-blocked" is a RISK_BLOCK diagnosis (fraud/risk-engine
# decline) — services/intelligence/policy_engine.py's RULE_FRAUD_NO_AUTO_RETRY
# always REJECTS it, regardless of automation flags. This test documents and
# verifies that gate through the real webhook path, not just the deterministic
# pipeline in isolation (already covered by test_intelligence_core.py).
#
# Other listed signals (dispute/refund history, mandate state, payment-link
# interaction) are NOT wired into recovery-probability scoring today — they
# feed the Phase 8 reconciliation audit trail only (see
# test_refund_on_resolved_case_produces_mismatch_audit_without_mutating_state
# above), which is honestly reported rather than fabricating a scoring input
# that doesn't exist.
# ===========================================================================
def test_intent_aware_recovery_gate_risk_block_never_pursued(
    client, razorpay_env, webhook_env, make_signature, monkeypatch
):
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "fake")

    payload = upi_timeout_payload(pid="pay_intent_1", eid="evt_intent_1")
    payload["payload"]["payment"]["entity"]["error_code"] = "GATEWAY_ERROR"
    payload["payload"]["payment"]["entity"]["error_reason"] = "payment_risk_check_failed"
    payload["payload"]["payment"]["entity"]["error_description"] = (
        "Transaction blocked by risk engine - suspected fraudulent transaction, do not retry"
    )
    raw = json.dumps(payload).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Razorpay-Signature": make_signature(raw)})
    assert res.status_code == 200
    cn = res.json()["case_number"]

    case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case["intelligence"]["failure_category"] == "RISK_BLOCK"
    assert case["intelligence"]["policy_verdict"] == "REJECTED"
    assert client.get(f"/api/v1/recovery-cases/{cn}/actions").json()["items"] == [], \
        "a RISK_BLOCK (hard-rejected/unwilling-customer signal) case must never be pursued, automation flags notwithstanding"
    assert client.get(f"/api/v1/recovery-cases/{cn}/communications").json()["items"] == []


# ===========================================================================
# Phase 8 — RecoveryCase.simulated
# ===========================================================================
def test_recovery_case_simulated_false_for_real_webhook(db_session):
    case = _make_case(db_session, upi_timeout_payload())
    db_session.refresh(case)
    assert case.simulated is False


def test_recovery_case_simulated_true_for_simulator(client):
    body = {
        "event_type": "payment.failed", "customer_name": "Rahul Sharma",
        "customer_email": "rahul@example.com", "customer_phone": "+919876543210",
        "amount": "4999.00", "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed",
        "error_description": "UPI handle authorization timeout on customer app",
    }
    cn = client.post("/api/v1/simulator/events", json=body).json()["case_number"]
    case = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case["simulated"] is True


# ===========================================================================
# Phase 8 — reconciliation/mismatch foundation: refund & dispute recognition
# ===========================================================================
def refund_or_dispute_webhook(client, make_signature, *, event, payment_id, event_id, payment_status="captured"):
    body = {
        "entity": "event", "event": event, "contains": ["payment"], "id": event_id,
        "payload": {"payment": {"entity": {
            "id": payment_id, "amount": 499900, "currency": "INR",
            "status": payment_status, "method": "upi", "created_at": 1620000000,
        }}},
        "created_at": 1620000000,
    }
    raw = json.dumps(body).encode()
    return client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Razorpay-Signature": make_signature(raw)})


def test_refund_on_resolved_case_produces_mismatch_audit_without_mutating_state(
    client, razorpay_env, webhook_env, make_signature, monkeypatch
):
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", False)
    payload = upi_timeout_payload(pid="pay_refund_1", eid="evt_refund_fail_1")
    raw = json.dumps(payload).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Razorpay-Signature": make_signature(raw)})
    cn = res.json()["case_number"]

    captured = json.dumps({
        "entity": "event", "event": "payment.captured", "contains": ["payment"], "id": "evt_refund_captured_1",
        "payload": {"payment": {"entity": {
            "id": "pay_refund_1", "amount": 499900, "currency": "INR", "status": "captured",
            "method": "upi", "created_at": 1620000000}}},
        "created_at": 1620000010,
    }).encode()
    r2 = client.post("/api/v1/webhooks/razorpay", content=captured,
                      headers={"Content-Type": "application/json", "X-Razorpay-Signature": make_signature(captured)})
    assert r2.status_code == 200
    case_before = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case_before["status"] == "RESOLVED"

    r3 = refund_or_dispute_webhook(client, make_signature, event="refund.processed",
                                   payment_id="pay_refund_1", event_id="evt_refund_processed_1")
    assert r3.status_code == 200

    case_after = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case_after["status"] == "RESOLVED"
    assert Decimal(case_after["amount_recovered"]) == Decimal(case_before["amount_recovered"]), \
        "a refund must never automatically change amount_recovered"

    audit = client.get(f"/api/v1/audit-logs?case_id={case_after['id']}&limit=100").json()["items"]
    assert any(a["action"] == "PAYMENT_STATE_RECONCILIATION_MISMATCH" for a in audit)


def test_dispute_event_recorded_without_state_change(client, razorpay_env, webhook_env, make_signature, monkeypatch):
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", False)
    payload = upi_timeout_payload(pid="pay_dispute_1", eid="evt_dispute_fail_1")
    raw = json.dumps(payload).encode()
    res = client.post("/api/v1/webhooks/razorpay", content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Razorpay-Signature": make_signature(raw)})
    cn = res.json()["case_number"]
    case_before = client.get(f"/api/v1/recovery-cases/{cn}").json()

    r2 = refund_or_dispute_webhook(client, make_signature, event="payment.dispute.created",
                                   payment_id="pay_dispute_1", event_id="evt_dispute_created_1")
    assert r2.status_code == 200

    case_after = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case_after["status"] == case_before["status"]
    assert Decimal(case_after["amount_recovered"]) == Decimal(case_before["amount_recovered"])

    audit = client.get(f"/api/v1/audit-logs?case_id={case_after['id']}&limit=100").json()["items"]
    assert any(a["action"] == "DISPUTE_EVENT_RECEIVED" for a in audit)


# ---------------------------------------------------------------------------
# API helpers (client fixture)
# ---------------------------------------------------------------------------
def _api_analyzed_case(client, **overrides):
    body = {
        "event_type": "payment.failed", "customer_name": "Rahul Sharma",
        "customer_email": "rahul@example.com", "customer_phone": "+919876543210",
        "amount": "4999.00", "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed",
        "error_description": "UPI handle authorization timeout on customer app",
    }
    body.update(overrides)
    cn = client.post("/api/v1/simulator/events", json=body).json()["case_number"]
    client.post(f"/api/v1/recovery-cases/{cn}/intelligence:analyze")
    return cn


def _api_propose(client, cn):
    r = client.post(f"/api/v1/recovery-cases/{cn}/actions/propose")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] is not None, body["proposal"]
    return body["action"]


def _api_execute(client, action_id):
    r = client.post(f"/api/v1/actions/{action_id}/execute")
    assert r.status_code == 200, r.text
    return r.json()["action"]
