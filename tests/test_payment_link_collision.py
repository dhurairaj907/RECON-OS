"""
RECON OS — Razorpay Payment Link reference-id collision / idempotency tests.

Production bug: RC-10006 reached Policy APPROVED / RETRY_DELAYED / eligible
for automatic execution, but Razorpay rejected Payment Link creation with
RAZORPAY_BAD_REQUEST: "payment link with given reference_id:
RECON-RC10006-ACT001 already exists." The executor had no path to reconcile
this — it just marked the action FAILED, orphaning a real, live Payment
Link and making every future retry fail identically forever.

Covers services/actions/collision.py + the new collision branch in
services/actions/executor.py, reusing test_actions.py's fixtures/helpers —
same convention as test_phase4_safety.py / test_communications_phase7.py.

Nothing here makes a real Razorpay call — `httpx.Client` is faked exactly
like test_actions.py's `razorpay_env` fixture (reused directly for every
test except D, which needs a call-by-call response sequence not offered by
the shared fixture, so it defines its own local, fully independent fake
client rather than modifying the shared one).
"""

from decimal import Decimal

import httpx
import pytest

from config import settings
from models.audit_log import AuditLog
from models.communication import Communication
from models.merchant import Merchant
from models.organization import Organization
from models.recovery_action import RecoveryAction
from services.actions.collision import (
    generate_collision_safe_reference,
    is_reference_collision,
)
from services.actions.executor import execute_action
from services.event_processor import process_inbound_event

from test_actions import (  # noqa: F401 — reused fixtures + helpers
    razorpay_env,
    webhook_env,
    upi_timeout_payload,
    _analyzed_case,
    _proposed_action,
    signed_payment_link_webhook,
)

COLLISION_ERROR_TEXT = (
    "payment link with given reference_id: RECON-RC10006-ACT001 already "
    "exists. Please create a payment link with a different reference_id."
)


def _collision_response(state, reference_id: str) -> None:
    state["status"] = 400
    state["body"] = {"error": {"description": (
        f"payment link with given reference_id: {reference_id} already "
        f"exists. Please create a payment link with a different reference_id."
    )}}


def _audit_actions(db, case_id) -> set[str]:
    return {a.action for a in db.query(AuditLog).filter_by(recovery_case_id=case_id).all()}


def _collide_then_succeed_client(new_link_id: str, search_items: list | None = None):
    """
    A fully independent fake httpx.Client (not the shared razorpay_env
    fixture, which only offers one static response for every call): the
    FIRST POST collides on reference_id, the SECOND POST (the bounded
    regenerated-reference retry) succeeds. GET (search) returns
    `search_items` — pass entries belonging to OTHER references to prove a
    collision is never reconciled against them.
    """
    calls: list = []

    class _Resp:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body

        def json(self):
            return self._body

    class _SequencedClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, auth=None, **k):
            calls.append(json["reference_id"])
            if len(calls) == 1:
                return _Resp(400, {"error": {"description": (
                    f"payment link with given reference_id: {json['reference_id']} "
                    f"already exists. Please create a payment link with a "
                    f"different reference_id."
                )}})
            return _Resp(200, {
                "id": new_link_id, "short_url": f"https://rzp.io/i/{new_link_id}",
                "status": "created", "reference_id": json["reference_id"],
                "amount": json["amount"], "currency": "INR",
            })

        def get(self, url, auth=None, **k):
            return _Resp(200, {"items": search_items or []})

    return _SequencedClient, calls


def _second_merchant(db) -> Merchant:
    org = Organization(name="Second Test Org")
    db.add(org)
    db.flush()
    merchant = Merchant(name="Second Test Merchant", organization_id=org.id)
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant


# ===========================================================================
# Pure helpers
# ===========================================================================
def test_is_reference_collision_matches_real_production_error():
    assert is_reference_collision(COLLISION_ERROR_TEXT) is True


def test_is_reference_collision_does_not_match_unrelated_bad_request():
    assert is_reference_collision("The amount must be at least INR 1.") is False
    assert is_reference_collision("Invalid customer email address.") is False
    assert is_reference_collision(None) is False
    assert is_reference_collision("") is False


def test_generate_collision_safe_reference_deterministic_and_incrementing():
    r1 = generate_collision_safe_reference("RECON-RC10006-ACT001")
    assert r1 == "RECON-RC10006-ACT001-R1"
    r2 = generate_collision_safe_reference(r1)
    assert r2 == "RECON-RC10006-ACT001-R2"
    # Deterministic: same input always produces the same output.
    assert generate_collision_safe_reference("RECON-RC10006-ACT001") == r1


# ===========================================================================
# A. First execution creates exactly one Payment Link.
# ===========================================================================
def test_a_first_execution_creates_one_payment_link(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "EXECUTED"
    assert result.outcome == "PENDING"
    assert result.provider_action_id is not None
    assert len(razorpay_env["calls"]) == 1


# ===========================================================================
# B. Re-running the same action does not create a second Payment Link.
# ===========================================================================
def test_b_rerun_does_not_create_second_payment_link(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    r1 = execute_action(db_session, action.id)
    r2 = execute_action(db_session, action.id)
    r3 = execute_action(db_session, action.id)
    assert r1.provider_action_id == r2.provider_action_id == r3.provider_action_id
    assert len(razorpay_env["calls"]) == 1
    assert "PAYMENT_LINK_REUSED" in _audit_actions(db_session, case.id)


# ===========================================================================
# C. Local failure + Razorpay duplicate reference -> existing matching
#    Payment Link is reconciled (test case that reproduces RC-10006).
# ===========================================================================
def test_c_collision_reconciles_with_existing_matching_link(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    reference = action.reference_id

    _collision_response(razorpay_env, reference)
    razorpay_env["search_items"] = [{
        "id": "plink_EXISTING001",
        "short_url": "https://rzp.io/i/EXISTING001",
        "status": "created",
        "reference_id": reference,
        "amount": action.amount_paise,
        "amount_paid": 0,
        "currency": "INR",
        "payments": [],
    }]

    result = execute_action(db_session, action.id)

    assert result.status == "EXECUTED"
    assert result.outcome == "PENDING"
    assert result.provider_action_id == "plink_EXISTING001"
    assert result.payment_link_url == "https://rzp.io/i/EXISTING001"
    # Exactly one POST was attempted (the one that collided) — no duplicate
    # create was ever issued.
    assert len(razorpay_env["calls"]) == 1

    audits = _audit_actions(db_session, case.id)
    assert "PAYMENT_LINK_REFERENCE_COLLISION" in audits
    assert "PAYMENT_LINK_REFERENCE_RECONCILED" in audits
    assert "PAYMENT_LINK_REFERENCE_REGENERATED" not in audits


# ===========================================================================
# D. Duplicate reference belonging to another action (not found in the
#    search) -> do NOT reuse it; generate a safe unique reference and create
#    a fresh Payment Link with it.
# ===========================================================================
def test_d_unverifiable_collision_regenerates_and_creates_new_link(db_session, razorpay_env, monkeypatch):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    original_reference = action.reference_id

    # Search finds nothing matching the original reference — cannot be
    # safely reconciled.
    client_cls, calls = _collide_then_succeed_client("plink_NEWLINK002", search_items=[])
    monkeypatch.setattr("integrations.razorpay.adapter.httpx.Client", client_cls)

    result = execute_action(db_session, action.id)

    assert result.status == "EXECUTED"
    assert result.provider_action_id == "plink_NEWLINK002"
    assert result.reference_id == f"{original_reference}-R1"
    assert result.reference_id != original_reference
    assert len(calls) == 2  # collided attempt + one regenerated retry, never more
    assert calls[0] == original_reference
    assert calls[1] == f"{original_reference}-R1"

    audits = _audit_actions(db_session, case.id)
    assert "PAYMENT_LINK_REFERENCE_COLLISION" in audits
    assert "PAYMENT_LINK_REFERENCE_REGENERATED" in audits
    assert "PAYMENT_LINK_REFERENCE_RECONCILED" not in audits

    regen_audit = (
        db_session.query(AuditLog)
        .filter_by(recovery_case_id=case.id, action="PAYMENT_LINK_REFERENCE_REGENERATED")
        .first()
    )
    assert regen_audit.metadata_json["original_reference_id"] == original_reference
    assert regen_audit.metadata_json["new_reference_id"] == f"{original_reference}-R1"


# ===========================================================================
# E. Existing Payment Link already paid -> do not create another; recovery
#    comes from Razorpay verification, never fabricated.
# ===========================================================================
def test_e_collision_with_already_paid_link_marks_recovered_via_verification(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    reference = action.reference_id
    expected_paise = action.amount_paise

    _collision_response(razorpay_env, reference)
    razorpay_env["search_items"] = [{
        "id": "plink_ALREADYPAID",
        "short_url": "https://rzp.io/i/ALREADYPAID",
        "status": "paid",
        "reference_id": reference,
        "amount": expected_paise,
        "amount_paid": expected_paise,
        "currency": "INR",
        "payments": [{"payment_id": "pay_x", "amount": expected_paise, "status": "captured"}],
    }]

    result = execute_action(db_session, action.id)

    assert result.status == "EXECUTED"
    assert result.outcome == "RECOVERED"
    assert Decimal(result.recovered_amount) == Decimal(expected_paise) / 100
    assert len(razorpay_env["calls"]) == 1  # never created a duplicate link

    db_session.refresh(case)
    assert case.status == "RESOLVED"

    audits = _audit_actions(db_session, case.id)
    assert "PAYMENT_LINK_REFERENCE_RECONCILED" in audits
    assert "RECOVERY_VERIFIED" in audits
    assert "RECOVERY_CASE_RESOLVED" in audits


# ===========================================================================
# F. Duplicate execution cannot send duplicate communications — neither a
#    plain retry of an EXECUTED action, nor a second call after a
#    collision-reconcile, ever double-sends.
# ===========================================================================
def test_f_no_duplicate_communications_on_retry(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)

    execute_action(db_session, action.id)
    first_count = db_session.query(Communication).filter_by(recovery_case_id=case.id).count()
    assert first_count > 0

    # Retry the now-EXECUTED action — must hit the idempotency guard, never
    # re-trigger the communication hook.
    execute_action(db_session, action.id)
    execute_action(db_session, action.id)
    second_count = db_session.query(Communication).filter_by(recovery_case_id=case.id).count()
    assert second_count == first_count


def test_f_no_duplicate_communications_after_collision_reconcile(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    reference = action.reference_id

    _collision_response(razorpay_env, reference)
    razorpay_env["search_items"] = [{
        "id": "plink_EXISTING_COMMS", "short_url": "https://rzp.io/i/E2",
        "status": "created", "reference_id": reference,
        "amount": action.amount_paise, "amount_paid": 0, "currency": "INR", "payments": [],
    }]

    execute_action(db_session, action.id)
    first_count = db_session.query(Communication).filter_by(recovery_case_id=case.id).count()
    assert first_count > 0

    # A second call now hits the plain idempotency guard (provider_action_id
    # is set) — must not send again.
    execute_action(db_session, action.id)
    second_count = db_session.query(Communication).filter_by(recovery_case_id=case.id).count()
    assert second_count == first_count


# ===========================================================================
# G. Organization isolation — a collision search for one org's action must
#    never reconcile with (or touch) another org's Payment Link, even when
#    that link is present in the same simulated Razorpay "recent links" list.
# ===========================================================================
def test_g_organization_isolation_never_reuses_another_orgs_link(db_session, razorpay_env, monkeypatch):
    merchant2 = _second_merchant(db_session)

    case1 = _analyzed_case(db_session, upi_timeout_payload(pid="pay_org1", eid="evt_org1"))
    action1 = _proposed_action(db_session, case1)

    # A second org's case/action, executed successfully first (normal
    # razorpay_env success mode) so it has a real Payment Link on Razorpay's
    # (simulated) side.
    payload2 = upi_timeout_payload(pid="pay_org2", eid="evt_org2")
    _, case2 = process_inbound_event(db=db_session, raw_payload=payload2, merchant_id=merchant2.id)
    from services.intelligence.orchestrator import run_intelligence
    run_intelligence(db_session, case2.id, trigger="test")
    db_session.refresh(case2)
    from services.actions.proposal import get_or_create_action
    action2, _ = get_or_create_action(db_session, case2)
    execute_action(db_session, action2.id)
    db_session.refresh(action2)
    assert action2.provider_action_id is not None
    assert action2.reference_id != action1.reference_id  # globally-unique case_number guarantees this

    # Now org1's action collides. Razorpay's "recent links" search returns
    # ONLY org2's link (a different reference_id) — org1's own reference is
    # not among the results, so it can never be reconciled against org2's
    # link. A second POST (the bounded regenerate retry) succeeds with a
    # brand new link. Uses its own sequenced client (not the shared
    # razorpay_env, whose static response can't represent "collide once,
    # then succeed" within a single execute_action() call).
    original_ref1 = action1.reference_id
    org2_provider_id_before = action2.provider_action_id
    org2_link = {
        "id": action2.provider_action_id, "short_url": action2.payment_link_url,
        "status": "created", "reference_id": action2.reference_id,
        "amount": action2.amount_paise, "amount_paid": 0, "currency": "INR", "payments": [],
    }
    client_cls, calls = _collide_then_succeed_client("plink_ORG1_NEWLINK", search_items=[org2_link])
    monkeypatch.setattr("integrations.razorpay.adapter.httpx.Client", client_cls)

    result1 = execute_action(db_session, action1.id)

    # Regenerated with a new, org1-owned reference — never adopted org2's link.
    assert result1.reference_id == f"{original_ref1}-R1"
    assert result1.provider_action_id != action2.provider_action_id

    audits1 = _audit_actions(db_session, case1.id)
    assert "PAYMENT_LINK_REFERENCE_REGENERATED" in audits1
    assert "PAYMENT_LINK_REFERENCE_RECONCILED" not in audits1

    # Org2's action is completely untouched.
    db_session.refresh(action2)
    assert action2.provider_action_id == org2_provider_id_before
    assert action2.status == "EXECUTED"


# ===========================================================================
# H. Existing simulator / full happy-path behaviour remains intact through
#    the refactored success path (_finalize_executed).
# ===========================================================================
def test_h_full_happy_path_through_simulated_recovery_still_works(db_session, razorpay_env, webhook_env, make_signature, client):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "EXECUTED"

    resp = signed_payment_link_webhook(
        client, make_signature, plink_id=result.provider_action_id,
        ref=result.reference_id, event_id="evt_sim_collision_h",
        amount=result.amount_paise, amount_paid=result.amount_paise,
    )
    assert resp.status_code == 200

    db_session.expire_all()
    refreshed = db_session.query(RecoveryAction).filter_by(id=action.id).first()
    assert refreshed.outcome == "RECOVERED"
