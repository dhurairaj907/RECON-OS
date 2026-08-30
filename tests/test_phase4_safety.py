"""
RECON OS — Phase 4 (P0) Tests: Human Approval Workflow + UNKNOWN Payment State

Nothing here makes a real Razorpay call — reuses the fake httpx client from
test_actions.py (`razorpay_env`), extended there with a GET /payment_links
(list/search) branch for `find_payment_link_by_reference`.

Two safety properties are exercised throughout:
  1. A human APPROVE never bypasses the Policy Engine — execute_action always
     re-derives context and re-evaluates policy fresh; approval only unlocks
     proceeding when that fresh check still allows it.
  2. An UNKNOWN outcome (ambiguous Razorpay timeout) is never auto-retried and
     is only ever resolved by asking Razorpay directly — never guessed.
"""

from decimal import Decimal

from models.audit_log import AuditLog
from models.payment import Payment
from models.recovery_action import RecoveryAction
from services.actions.approval import approve_action, reject_action
from services.actions.common import ui_state
from services.actions.executor import execute_action
from services.actions.unknown import verify_unknown_action

from test_actions import (  # noqa: F401 — re-used fixtures + helpers
    razorpay_env,
    upi_timeout_payload,
    _analyzed_case,
    _proposed_action,
    _api_analyzed_case,
    _api_propose,
    _api_execute,
)


def _high_value_case(db_session):
    """₹14,999 card decline -> policy NEEDS_APPROVAL (RULE_HIGH_VALUE_APPROVAL)."""
    payload = {
        "entity": "event", "event": "payment.failed", "contains": ["payment"],
        "id": "evt_hv_p4_1",
        "payload": {"payment": {"entity": {
            "id": "pay_hv_p4_1", "amount": 1499900, "currency": "INR", "status": "failed",
            "method": "card", "email": "hv@x.com", "error_code": "GATEWAY_ERROR",
            "error_reason": "payment_failed",
            "error_description": "Transaction declined: insufficient funds / limit exceeded",
            "created_at": 1620000000,
        }}}, "created_at": 1620000000,
    }
    return _analyzed_case(db_session, payload)


# ===========================================================================
# 1-11. Human Approval Workflow
# ===========================================================================
def test_needs_approval_action_can_be_approved_and_executes(db_session, razorpay_env):
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    blocked = execute_action(db_session, action.id)
    assert blocked.status == "BLOCKED" and blocked.blocked_reason == "NEEDS_APPROVAL"

    approved = approve_action(db_session, action.id)
    assert approved.status == "EXECUTED"
    assert approved.outcome == "PENDING"
    assert approved.provider_action_id.startswith("plink_")
    assert len(razorpay_env["calls"]) == 1


def test_approve_records_human_decision_fields(db_session, razorpay_env):
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    approved = approve_action(db_session, action.id, decided_by="ops@recon.test")
    assert approved.human_decision == "APPROVED"
    assert approved.human_decided_at is not None
    assert approved.human_decided_by == "ops@recon.test"


def test_reject_is_terminal_and_never_executes(db_session, razorpay_env):
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    rejected = reject_action(db_session, action.id, decided_by="ops@recon.test", reason="Suspicious pattern")
    assert rejected.status == "BLOCKED"
    assert rejected.blocked_reason == "HUMAN_REJECTED"
    assert rejected.human_decision == "REJECTED"
    assert len(razorpay_env["calls"]) == 0

    # Terminal — even re-running execution does not proceed (still no decision honoured).
    still_blocked = execute_action(db_session, action.id)
    assert still_blocked.status == "BLOCKED"
    assert len(razorpay_env["calls"]) == 0


def test_approve_is_idempotent_no_duplicate_execution(db_session, razorpay_env):
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    r1 = approve_action(db_session, action.id)
    r2 = approve_action(db_session, action.id)
    r3 = approve_action(db_session, action.id)
    assert r1.provider_action_id == r2.provider_action_id == r3.provider_action_id
    assert len(razorpay_env["calls"]) == 1


def test_reject_is_idempotent(db_session, razorpay_env):
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    reject_action(db_session, action.id)
    r2 = reject_action(db_session, action.id)
    assert r2.status == "BLOCKED" and r2.blocked_reason == "HUMAN_REJECTED"


def test_approval_revalidates_and_blocks_if_policy_now_rejected(db_session, razorpay_env):
    """
    Between the NEEDS_APPROVAL block and the human's approve click, the real
    payment state becomes unverifiable — approval must NOT execute on stale
    state; the fresh re-evaluation (now REJECTED) wins.
    """
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    payment = db_session.query(Payment).filter_by(id=case.payment_id).first()
    payment.status = "unknown"
    db_session.commit()

    approved = approve_action(db_session, action.id)
    assert approved.status == "BLOCKED"
    assert approved.blocked_reason == "POLICY_REJECTED"
    assert len(razorpay_env["calls"]) == 0
    # a REJECTED re-evaluation clears any stale human decision
    assert approved.human_decision is None


def test_approve_on_already_executed_action_is_noop(db_session, razorpay_env):
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    approve_action(db_session, action.id)
    assert len(razorpay_env["calls"]) == 1
    again = approve_action(db_session, action.id)   # already EXECUTED
    assert again.status == "EXECUTED"
    assert len(razorpay_env["calls"]) == 1           # no second Razorpay call


def test_reject_on_already_executed_action_is_noop(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())   # auto-approved, executes directly
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    result = reject_action(db_session, action.id)
    assert result.status == "EXECUTED"                # untouched — reject on an executed action is a no-op
    assert result.human_decision is None


def test_approval_audit_trail_records_grant_and_honor(db_session, razorpay_env):
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    approve_action(db_session, action.id)
    events = {a.action for a in db_session.query(AuditLog).filter(
        AuditLog.recovery_case_id == case.id).all()}
    assert "ACTION_APPROVAL_GRANTED" in events
    assert "ACTION_APPROVAL_HONORED" in events


def test_reject_audit_trail_records_decision(db_session, razorpay_env):
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    reject_action(db_session, action.id, reason="Customer disputed the charge")
    log = db_session.query(AuditLog).filter(
        AuditLog.recovery_case_id == case.id,
        AuditLog.action == "ACTION_REJECTED_BY_HUMAN").first()
    assert log is not None
    assert "Customer disputed the charge" in log.detail


def test_human_approval_never_overrides_rejected_verdict(db_session, razorpay_env):
    """Mirrors test_ai_cannot_bypass_policy but for a human decision: even a
    recorded APPROVED decision cannot survive a fresh REJECTED re-evaluation."""
    case = _high_value_case(db_session)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    action.human_decision = "APPROVED"   # simulate a stale prior approval
    db_session.commit()

    payment = db_session.query(Payment).filter_by(id=case.payment_id).first()
    payment.status = "unknown"
    db_session.commit()

    result = execute_action(db_session, action.id)
    assert result.status == "BLOCKED"
    assert result.blocked_reason == "POLICY_REJECTED"
    assert len(razorpay_env["calls"]) == 0


# ===========================================================================
# 12-23. UNKNOWN payment state / timeout safety
# ===========================================================================
def test_timeout_marks_outcome_unknown_not_failed(db_session, razorpay_env):
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.outcome == "UNKNOWN"
    assert result.status != "FAILED"
    assert result.status == "EXECUTING"
    assert result.error_code == "RAZORPAY_TIMEOUT"


def test_unknown_outcome_blocks_blind_retry(db_session, razorpay_env):
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    assert len(razorpay_env["calls"]) == 1

    # A second execute_action call — e.g. an operator clicking "retry" — must
    # NOT issue a second Razorpay call. The existing EXECUTING-status
    # idempotency guard blocks it with zero special-casing.
    again = execute_action(db_session, action.id)
    assert again.outcome == "UNKNOWN"
    assert len(razorpay_env["calls"]) == 1


def test_unknown_ui_state_is_distinct_from_failed(db_session, razorpay_env):
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert ui_state(result) == "UNKNOWN"
    assert ui_state(result) != "FAILED"


def test_verify_unknown_resolves_to_executed_when_found(db_session, razorpay_env):
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    assert action.outcome == "UNKNOWN"

    razorpay_env["mode"] = "success"
    razorpay_env["search_items"] = [{
        "id": "plink_FOUND_1", "short_url": "https://rzp.io/i/FOUND",
        "status": "created", "reference_id": action.reference_id,
        "amount": action.amount_paise, "amount_paid": 0, "currency": "INR",
        "payments": [],
    }]

    resolved = verify_unknown_action(db_session, action.id)
    assert resolved.status == "EXECUTED"
    assert resolved.outcome == "PENDING"
    assert resolved.provider_action_id == "plink_FOUND_1"
    assert resolved.payment_link_url == "https://rzp.io/i/FOUND"
    assert len(razorpay_env["calls"]) == 1   # no duplicate create


def test_verify_unknown_resolves_to_failed_when_not_found(db_session, razorpay_env):
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    razorpay_env["mode"] = "success"
    razorpay_env["search_items"] = []   # confirmed: nothing on Razorpay's side

    resolved = verify_unknown_action(db_session, action.id)
    assert resolved.status == "FAILED"
    assert resolved.outcome == "FAILED"
    assert resolved.error_code == "RAZORPAY_TIMEOUT_VERIFIED_NOT_CREATED"

    # Now a verified fact, not a guess — a fresh attempt is safe and policy-gated.
    retry = execute_action(db_session, resolved.id)
    assert retry.status == "EXECUTED"
    assert len(razorpay_env["calls"]) == 2   # the original timeout + this real create


def test_verify_unknown_stays_unknown_when_verification_inconclusive(db_session, razorpay_env):
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    # Verification search itself times out — RECON must never guess.
    resolved = verify_unknown_action(db_session, action.id)
    assert resolved.outcome == "UNKNOWN"
    assert resolved.status == "EXECUTING"


def test_verify_unknown_never_bypasses_policy(db_session, razorpay_env):
    """Once resolved to FAILED, a retry still goes through the real Policy
    Engine — resolution never grants a bypass."""
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    razorpay_env["mode"] = "success"
    razorpay_env["search_items"] = []
    resolved = verify_unknown_action(db_session, action.id)
    assert resolved.status == "FAILED"

    payment = db_session.query(Payment).filter_by(id=case.payment_id).first()
    payment.status = "unknown"
    db_session.commit()

    retry = execute_action(db_session, resolved.id)
    assert retry.status == "BLOCKED"
    assert retry.blocked_reason == "POLICY_REJECTED"


def test_unknown_audit_trail_records_uncertainty(db_session, razorpay_env):
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    events = {a.action for a in db_session.query(AuditLog).filter(
        AuditLog.recovery_case_id == case.id).all()}
    assert "ACTION_OUTCOME_UNKNOWN" in events

    verify_unknown_action(db_session, action.id)   # still inconclusive (mode still timeout)
    events2 = {a.action for a in db_session.query(AuditLog).filter(
        AuditLog.recovery_case_id == case.id).all()}
    assert "UNKNOWN_VERIFICATION_STARTED" in events2
    assert "UNKNOWN_VERIFICATION_INCONCLUSIVE" in events2


def test_verify_unknown_is_idempotent_when_already_resolved(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    executed = execute_action(db_session, action.id)   # succeeds normally, not UNKNOWN
    assert executed.status == "EXECUTED"

    result = verify_unknown_action(db_session, executed.id)   # not UNKNOWN — no-op
    assert result.status == "EXECUTED"
    assert result.provider_action_id == executed.provider_action_id


def test_unknown_outcome_never_double_counts_as_recovered(db_session, razorpay_env):
    """An UNKNOWN action must never be reachable via the normal recovered-amount
    path until it is explicitly resolved."""
    razorpay_env["mode"] = "timeout"
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert Decimal(result.recovered_amount or 0) == Decimal("0.00")
    db_session.refresh(case)
    assert case.status != "RESOLVED"


# ===========================================================================
# End-to-end (API): full approval chain, full timeout->unknown->verify chain
# ===========================================================================
def test_e2e_full_approval_chain(client, razorpay_env):
    cn = _api_analyzed_case(client, amount="14999.00", customer_email="hv-e2e@x.com",
                            error_description="Transaction declined: insufficient funds / limit exceeded")
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])
    assert executed["status"] == "BLOCKED"
    assert executed["blocked_reason"] == "NEEDS_APPROVAL"
    assert executed["ui_state"] == "NEEDS_APPROVAL"

    res = client.post(f"/api/v1/actions/{action['id']}/approve")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    a = body["action"]
    assert a["status"] == "EXECUTED"
    assert a["ui_state"] == "WAITING_FOR_PAYMENT"
    assert a["human_decision"] == "APPROVED"
    assert a["human_decided_at"] is not None
    assert a["payment_link_url"]

    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    events = {x["action"] for x in audits}
    assert {"ACTION_APPROVAL_GRANTED", "ACTION_APPROVAL_HONORED", "ACTION_APPROVED",
            "PAYMENT_LINK_CREATED"}.issubset(events)


def test_e2e_reject_via_api_never_executes(client, razorpay_env):
    cn = _api_analyzed_case(client, amount="14999.00", customer_email="hv-e2e-2@x.com",
                            error_description="Transaction declined: insufficient funds / limit exceeded")
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])

    res = client.post(f"/api/v1/actions/{action['id']}/reject")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    a = body["action"]
    assert a["status"] == "BLOCKED"
    assert a["blocked_reason"] == "HUMAN_REJECTED"
    assert a["ui_state"] == "BLOCKED"
    assert len(razorpay_env["calls"]) == 0


def test_e2e_full_timeout_to_unknown_to_verification_chain(client, razorpay_env):
    razorpay_env["mode"] = "timeout"
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])
    assert executed["outcome"] == "UNKNOWN"
    assert executed["ui_state"] == "UNKNOWN"
    assert executed["status"] != "FAILED"

    razorpay_env["mode"] = "success"
    razorpay_env["search_items"] = [{
        "id": "plink_E2E_FOUND", "short_url": "https://rzp.io/i/E2EFOUND",
        "status": "created", "reference_id": executed["reference_id"],
        "amount": 499900, "amount_paid": 0, "currency": "INR", "payments": [],
    }]

    res = client.post(f"/api/v1/actions/{action['id']}/verify-unknown")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    a = body["action"]
    assert a["status"] == "EXECUTED"
    assert a["outcome"] == "PENDING"
    assert a["ui_state"] == "WAITING_FOR_PAYMENT"
    assert a["provider_action_id"] == "plink_E2E_FOUND"

    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    events = {x["action"] for x in audits}
    assert {"ACTION_OUTCOME_UNKNOWN", "UNKNOWN_VERIFICATION_STARTED",
            "UNKNOWN_RESOLVED_SUCCESS"}.issubset(events)
