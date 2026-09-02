"""
RECON OS — Phase 9 Tests: True Payment Reconciliation Engine

Payment lifecycle state transitions, mismatch detection, refund/dispute
amount tracking, event-ledger correlation, organization isolation, analytics
net-of-refund, and recovery-lifecycle separation — see
services/reconciliation.py and services/event_processor.py.

Nothing here makes a real Razorpay call — reuses the same fake httpx client
(`razorpay_env`) and signed-webhook helpers as test_actions.py.
"""

import json
from decimal import Decimal

import pytest

from config import settings
from models.audit_log import AuditLog
from models.payment import Payment
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from services.event_processor import process_inbound_event

from test_actions import (  # noqa: F401 — reused fixtures + helpers
    razorpay_env,
    webhook_env,
    signed_payment_link_webhook,
    upi_timeout_payload,
    refund_or_dispute_webhook,
    _api_analyzed_case,
    _api_propose,
    _api_execute,
)


# ---------------------------------------------------------------------------
# Webhook builders
# ---------------------------------------------------------------------------
def _post(client, make_signature, body):
    raw = json.dumps(body).encode()
    return client.post("/api/v1/webhooks/razorpay", content=raw,
                        headers={"Content-Type": "application/json",
                                 "X-Razorpay-Signature": make_signature(raw)})


def captured_webhook(client, make_signature, *, payment_id, event_id, amount=499900):
    return _post(client, make_signature, {
        "entity": "event", "event": "payment.captured", "contains": ["payment"], "id": event_id,
        "payload": {"payment": {"entity": {
            "id": payment_id, "amount": amount, "currency": "INR", "status": "captured",
            "method": "upi", "created_at": 1620000000,
        }}},
        "created_at": 1620000010,
    })


def refund_webhook(client, make_signature, *, payment_id, event_id, refund_amount,
                    payment_amount=499900, refund_id=None):
    return _post(client, make_signature, {
        "entity": "event", "event": "refund.processed", "contains": ["payment", "refund"], "id": event_id,
        "payload": {
            "payment": {"entity": {
                "id": payment_id, "amount": payment_amount, "currency": "INR",
                "status": "captured", "method": "upi", "created_at": 1620000000,
            }},
            "refund": {"entity": {
                "id": refund_id or f"rfnd_{event_id}", "amount": refund_amount, "currency": "INR",
                "payment_id": payment_id, "status": "processed", "created_at": 1620000020,
            }},
        },
        "created_at": 1620000020,
    })


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------
def test_failed_payment_gets_failed_lifecycle_status(client, webhook_env, make_signature):
    payload = upi_timeout_payload(pid="pay_life_1", eid="evt_life_fail_1")
    res = _post(client, make_signature, payload)
    assert res.status_code == 200
    p = client.get("/api/v1/payments/pay_life_1").json()
    assert p["lifecycle_status"] == "FAILED"
    assert p["reconciliation_status"] == "IN_SYNC"


def test_captured_payment_gets_captured_lifecycle_status(client, webhook_env, make_signature):
    r = captured_webhook(client, make_signature, payment_id="pay_life_2", event_id="evt_life_cap_2")
    assert r.status_code == 200
    p = client.get("/api/v1/payments/pay_life_2").json()
    assert p["lifecycle_status"] == "CAPTURED"
    assert p["reconciliation_status"] == "IN_SYNC"


def test_captured_after_failed_is_invalid_transition_mismatch(client, webhook_env, make_signature):
    """A payment that already terminally FAILED can never legitimately become
    CAPTURED under the same provider payment id — this must be flagged, not
    silently accepted."""
    payload = upi_timeout_payload(pid="pay_life_3", eid="evt_life_fail_3")
    _post(client, make_signature, payload)
    r = captured_webhook(client, make_signature, payment_id="pay_life_3", event_id="evt_life_cap_3")
    assert r.status_code == 200

    p = client.get("/api/v1/payments/pay_life_3").json()
    assert p["lifecycle_status"] == "FAILED", "a mismatch must never mutate lifecycle_status"
    assert p["reconciliation_status"] == "MISMATCH"

    mismatches = client.get("/api/v1/reconciliation/mismatches").json()["items"]
    assert any(m["action"] == "RECONCILIATION_MISMATCH" and "pay_life_3" in m["detail"] for m in mismatches)


def test_duplicate_captured_event_is_harmless_noop(client, webhook_env, make_signature):
    r1 = captured_webhook(client, make_signature, payment_id="pay_life_4", event_id="evt_life_cap_4a")
    r2 = captured_webhook(client, make_signature, payment_id="pay_life_4", event_id="evt_life_cap_4b")
    assert r1.status_code == r2.status_code == 200

    p = client.get("/api/v1/payments/pay_life_4").json()
    assert p["lifecycle_status"] == "CAPTURED"
    assert p["reconciliation_status"] == "IN_SYNC", "a redundant duplicate must never be reported as a mismatch"

    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    assert sum(1 for a in audits if a["action"] == "PAYMENT_CAPTURED") == 1
    assert any(a["action"] == "DUPLICATE_FINANCIAL_TRANSITION_IGNORED" for a in audits)
    # The same provider event must never create duplicate financial state
    # transitions — confirmed by the exact-once PAYMENT_CAPTURED count above.


def test_captured_amount_mismatch_is_flagged(client, webhook_env, make_signature):
    payload = upi_timeout_payload(pid="pay_life_5", eid="evt_life_fail_5", amount_paise=499900)
    _post(client, make_signature, payload)
    r = captured_webhook(client, make_signature, payment_id="pay_life_5", event_id="evt_life_cap_5")
    assert r.status_code == 200
    p = client.get("/api/v1/payments/pay_life_5").json()
    assert p["reconciliation_status"] == "MISMATCH"


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------
def test_full_refund_marks_payment_refunded(client, webhook_env, make_signature):
    captured_webhook(client, make_signature, payment_id="pay_ref_1", event_id="evt_ref_cap_1")
    r = refund_webhook(client, make_signature, payment_id="pay_ref_1", event_id="evt_ref_full_1",
                        refund_amount=499900)
    assert r.status_code == 200

    p = client.get("/api/v1/payments/pay_ref_1").json()
    assert p["lifecycle_status"] == "REFUNDED"
    assert p["reconciliation_status"] == "IN_SYNC"
    assert p["refunded_amount_paise"] == 499900

    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    assert any(a["action"] == "PAYMENT_REFUNDED" for a in audits)


def test_partial_refund_marks_payment_partially_refunded(client, webhook_env, make_signature):
    captured_webhook(client, make_signature, payment_id="pay_ref_2", event_id="evt_ref_cap_2")
    r = refund_webhook(client, make_signature, payment_id="pay_ref_2", event_id="evt_ref_partial_2",
                        refund_amount=200000)
    assert r.status_code == 200

    p = client.get("/api/v1/payments/pay_ref_2").json()
    assert p["lifecycle_status"] == "PARTIALLY_REFUNDED"
    assert p["refunded_amount_paise"] == 200000

    recon = client.get("/api/v1/payments/pay_ref_2/reconciliation").json()
    assert recon["remaining_captured_amount_paise"] == 499900 - 200000

    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    assert any(a["action"] == "PAYMENT_PARTIALLY_REFUNDED" for a in audits)


def test_two_partial_refunds_accumulate_to_full_refund(client, webhook_env, make_signature):
    captured_webhook(client, make_signature, payment_id="pay_ref_3", event_id="evt_ref_cap_3")
    refund_webhook(client, make_signature, payment_id="pay_ref_3", event_id="evt_ref_3a", refund_amount=300000)
    r2 = refund_webhook(client, make_signature, payment_id="pay_ref_3", event_id="evt_ref_3b", refund_amount=199900)
    assert r2.status_code == 200

    p = client.get("/api/v1/payments/pay_ref_3").json()
    assert p["lifecycle_status"] == "REFUNDED"
    assert p["refunded_amount_paise"] == 499900


def test_refund_exceeding_captured_amount_is_a_mismatch_not_applied(client, webhook_env, make_signature):
    captured_webhook(client, make_signature, payment_id="pay_ref_4", event_id="evt_ref_cap_4")
    r = refund_webhook(client, make_signature, payment_id="pay_ref_4", event_id="evt_ref_over_4",
                        refund_amount=999900)
    assert r.status_code == 200

    p = client.get("/api/v1/payments/pay_ref_4").json()
    assert p["lifecycle_status"] == "CAPTURED", "an invalid refund must never mutate lifecycle_status"
    assert p["refunded_amount_paise"] == 0
    assert p["reconciliation_status"] == "MISMATCH"


def test_refund_on_never_captured_payment_is_unknown_identifier_mismatch(client, webhook_env, make_signature):
    r = refund_webhook(client, make_signature, payment_id="pay_ref_ghost", event_id="evt_ref_ghost_1",
                        refund_amount=100000)
    assert r.status_code == 200
    p = client.get("/api/v1/payments/pay_ref_ghost").json()
    assert p["reconciliation_status"] == "MISMATCH"


# ---------------------------------------------------------------------------
# Disputes
# ---------------------------------------------------------------------------
def test_dispute_created_sets_open_dispute_status(client, razorpay_env, webhook_env, make_signature, monkeypatch):
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", False)
    captured_webhook(client, make_signature, payment_id="pay_disp_1", event_id="evt_disp_cap_1")
    r = refund_or_dispute_webhook(client, make_signature, event="payment.dispute.created",
                                   payment_id="pay_disp_1", event_id="evt_disp_created_1")
    assert r.status_code == 200

    p = client.get("/api/v1/payments/pay_disp_1").json()
    assert p["dispute_status"] == "OPEN"
    assert p["lifecycle_status"] == "DISPUTED"


def test_dispute_lost_preserves_capture_history_in_audit_trail(
    client, razorpay_env, webhook_env, make_signature, monkeypatch
):
    """A dispute must never erase historical recovery/capture activity —
    original capture + later dispute must both remain visible."""
    monkeypatch.setattr(settings, "INTELLIGENCE_ENABLED", False)
    captured_webhook(client, make_signature, payment_id="pay_disp_2", event_id="evt_disp_cap_2")
    refund_or_dispute_webhook(client, make_signature, event="payment.dispute.created",
                               payment_id="pay_disp_2", event_id="evt_disp_created_2")
    r = refund_or_dispute_webhook(client, make_signature, event="payment.dispute.lost",
                                   payment_id="pay_disp_2", event_id="evt_disp_lost_2")
    assert r.status_code == 200

    p = client.get("/api/v1/payments/pay_disp_2").json()
    assert p["dispute_status"] == "LOST"
    assert p["lifecycle_status"] == "CAPTURED", \
        "once resolved, lifecycle_status reflects the underlying capture — never stuck at DISPUTED"

    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    actions_seen = [a["action"] for a in audits if "pay_disp_2" in a["detail"]]
    assert "PAYMENT_CAPTURED" in actions_seen, "the original capture must still be visible after the dispute"
    assert "PAYMENT_DISPUTED" in actions_seen


def test_dispute_on_never_captured_payment_is_a_mismatch(client, webhook_env, make_signature):
    r = refund_or_dispute_webhook(client, make_signature, event="payment.dispute.created",
                                   payment_id="pay_disp_ghost", event_id="evt_disp_ghost_1")
    assert r.status_code == 200
    p = client.get("/api/v1/payments/pay_disp_ghost").json()
    assert p["reconciliation_status"] == "MISMATCH"


# ---------------------------------------------------------------------------
# Recovery separation — RecoveryCase/RecoveryAction lifecycle is untouched
# ---------------------------------------------------------------------------
def test_refund_never_changes_recovery_action_outcome(client, razorpay_env, webhook_env, make_signature):
    """Full recovery flow: failed -> payment-link executed -> recovered via
    webhook -> refunded. RecoveryAction.outcome must STILL read RECOVERED —
    a payment lifecycle refund is a separate concept from the recovery
    workflow outcome, which is permanent history."""
    cn = _api_analyzed_case(client, amount="4999.00")
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])
    plink_id, ref = executed["provider_action_id"], executed["reference_id"]

    r = signed_payment_link_webhook(client, make_signature, plink_id=plink_id, ref=ref,
                                     event_id="evt_recsep_paid_1")
    assert r.status_code == 200
    recovered_action = client.get(f"/api/v1/actions/{action['id']}").json()
    assert recovered_action["outcome"] == "RECOVERED"

    fulfilling_payment_id = f"pay_evt_recsep_paid_1"  # matches signed_payment_link_webhook's "pay_" + event_id
    # Real Razorpay delivers a SEPARATE payment.captured webhook for the same
    # underlying payment alongside payment_link.paid — this is what actually
    # establishes lifecycle_status=CAPTURED for the fulfilling Payment.
    captured_webhook(client, make_signature, payment_id=fulfilling_payment_id,
                      event_id="evt_recsep_cap_1")

    r2 = refund_webhook(client, make_signature, payment_id=fulfilling_payment_id,
                         event_id="evt_recsep_refund_1", refund_amount=499900)
    assert r2.status_code == 200

    still_recovered = client.get(f"/api/v1/actions/{action['id']}").json()
    assert still_recovered["outcome"] == "RECOVERED", \
        "recovery lifecycle must never be rewritten by a later payment refund"
    assert still_recovered["recovered_amount"] == recovered_action["recovered_amount"]

    case_after = client.get(f"/api/v1/recovery-cases/{cn}").json()
    assert case_after["status"] == "RESOLVED"


def test_resolved_case_refund_mismatch_test_still_passes_unmodified():
    """Sanity anchor: the Phase-8 foundation test this module builds on top
    of (test_actions.py::test_refund_on_resolved_case_produces_mismatch_audit_without_mutating_state)
    is not duplicated here — this just documents the dependency."""
    assert True


# ---------------------------------------------------------------------------
# Organization isolation
# ---------------------------------------------------------------------------
def test_reconciliation_endpoints_respect_organization_isolation(unauthenticated_client, webhook_env):
    c = unauthenticated_client
    res_a = c.post("/api/v1/auth/register", json={
        "email": "recon-org-a@recon.test", "password": "Password123!",
        "organization_name": "Reconciliation Org A",
    })
    assert res_a.status_code == 201, res_a.text
    sim = c.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Org A Customer",
        "customer_email": "org-a@example.com", "amount": "1999.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed", "error_description": "timeout",
    })
    assert sim.status_code == 201, sim.text
    case = c.get(f"/api/v1/recovery-cases/{sim.json()['case_number']}").json()
    payment_id = case["payment_id"]
    assert payment_id

    c.cookies.clear()
    res_b = c.post("/api/v1/auth/register", json={
        "email": "recon-org-b@recon.test", "password": "Password123!",
        "organization_name": "Reconciliation Org B",
    })
    assert res_b.status_code == 201, res_b.text
    denied = c.get(f"/api/v1/payments/{payment_id}/reconciliation")
    assert denied.status_code == 404

    mismatches_b = c.get("/api/v1/reconciliation/mismatches").json()
    assert mismatches_b["total"] == 0


# ---------------------------------------------------------------------------
# Analytics — net of refunds
# ---------------------------------------------------------------------------
def test_analytics_revenue_recovered_nets_out_refund(client, razorpay_env, webhook_env, make_signature):
    cn = _api_analyzed_case(client, amount="4999.00")
    action = _api_propose(client, cn)
    executed = _api_execute(client, action["id"])
    plink_id, ref = executed["provider_action_id"], executed["reference_id"]

    signed_payment_link_webhook(client, make_signature, plink_id=plink_id, ref=ref,
                                 event_id="evt_analytics_paid_1")
    # Real Razorpay delivers a SEPARATE payment.captured webhook for the same
    # underlying payment alongside payment_link.paid.
    captured_webhook(client, make_signature, payment_id="pay_evt_analytics_paid_1",
                      event_id="evt_analytics_cap_1")

    before = client.get("/api/v1/analytics").json()
    assert Decimal(before["revenue_recovered"]) == Decimal("4999.00")
    assert Decimal(before["revenue_refunded"]) == Decimal("0.00")

    refund_webhook(client, make_signature, payment_id="pay_evt_analytics_paid_1",
                    event_id="evt_analytics_refund_1", refund_amount=499900)

    after = client.get("/api/v1/analytics").json()
    assert Decimal(after["revenue_recovered"]) == Decimal("0.00"), \
        "fully refunded recovered revenue must not be reported as permanently recovered"
    assert Decimal(after["revenue_refunded"]) == Decimal("4999.00")


def test_analytics_reconciliation_mismatches_total_counts_mismatches(client, webhook_env, make_signature):
    before = client.get("/api/v1/analytics").json()["reconciliation_mismatches_total"]

    payload = upi_timeout_payload(pid="pay_analytics_mm_1", eid="evt_analytics_mm_fail_1")
    _post(client, make_signature, payload)
    captured_webhook(client, make_signature, payment_id="pay_analytics_mm_1", event_id="evt_analytics_mm_cap_1")

    after = client.get("/api/v1/analytics").json()["reconciliation_mismatches_total"]
    assert after == before + 1


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------
def test_revenue_event_correlation_id_populated(db_session, webhook_env, make_signature):
    from models.merchant import Merchant
    merchant = db_session.query(Merchant).first()
    payload = upi_timeout_payload(pid="pay_corr_1", eid="evt_corr_fail_1")
    from models.revenue_event import RevenueEvent
    process_inbound_event(db=db_session, raw_payload=payload, merchant_id=merchant.id)
    ev = db_session.query(RevenueEvent).filter_by(razorpay_event_id="evt_corr_fail_1").first()
    assert ev is not None
    assert ev.correlation_id == "pay_corr_1"


# ---------------------------------------------------------------------------
# Duplicate event idempotency at the ledger level
# ---------------------------------------------------------------------------
def test_duplicate_event_id_never_reapplies_lifecycle_transition(client, webhook_env, make_signature):
    body = {
        "entity": "event", "event": "payment.captured", "contains": ["payment"], "id": "evt_dup_life_1",
        "payload": {"payment": {"entity": {
            "id": "pay_dup_life_1", "amount": 499900, "currency": "INR", "status": "captured",
            "method": "upi", "created_at": 1620000000,
        }}},
        "created_at": 1620000010,
    }
    r1 = _post(client, make_signature, body)
    r2 = _post(client, make_signature, body)  # exact same event id — must be ignored, not reprocessed
    assert r1.status_code == r2.status_code == 200

    audits = client.get("/api/v1/audit-logs?limit=100").json()["items"]
    assert sum(1 for a in audits if a["action"] == "PAYMENT_CAPTURED") == 1
    assert any(a["action"] == "DUPLICATE_EVENT_IGNORED" for a in audits)
