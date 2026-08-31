"""
RECON OS — Phase 5: Recovery Communications tests.

Covers the provider abstraction (fake providers never claim real delivery),
the policy-reuse decision function (never bypasses Policy Engine / human
approval), contact-info / opt-out / duplicate / rate-limit gating, and the
audit trail. Uses the same DB-isolation helpers as test_actions.py.
"""

from datetime import datetime, timedelta, timezone

from config import settings
from models.audit_log import AuditLog
from models.communication import Communication
from services.actions.executor import execute_action
from services.communications.providers import (
    FakeEmailProvider, FakeSMSProvider, FakeWhatsAppProvider, get_communication_provider,
)
from services.communications.service import decide_communication, send_communication

from test_actions import (  # noqa: F401 — reused fixtures + helpers
    razorpay_env,
    upi_timeout_payload,
    _analyzed_case,
    _proposed_action,
)


def _get_merchant_id(db, case):
    return case.merchant_id


# ===========================================================================
# Fake providers — never claim real delivery
# ===========================================================================
def test_fake_email_provider_sends_and_never_claims_delivered():
    result = FakeEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is True
    assert result.status == "SENT"          # never "DELIVERED" — that's a real confirmation only
    assert result.provider == "FAKE_EMAIL"
    assert result.provider_message_id


def test_fake_sms_provider_sends():
    result = FakeSMSProvider().send(to="+911234567890", subject="", body="b")
    assert result.ok is True and result.status == "SENT" and result.provider == "FAKE_SMS"


def test_fake_whatsapp_provider_sends():
    result = FakeWhatsAppProvider().send(to="+911234567890", subject="", body="b")
    assert result.ok is True and result.status == "SENT" and result.provider == "FAKE_WHATSAPP"


def test_default_mode_uses_fake_providers():
    assert settings.RECON_COMMUNICATIONS_MODE == "fake"
    assert get_communication_provider("EMAIL").name == "FAKE_EMAIL"


def test_real_provider_without_credentials_fails_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    provider = get_communication_provider("EMAIL")
    result = provider.send(to="a@b.com", subject="s", body="b")
    assert result.ok is False
    assert result.error_code == "NOT_CONFIGURED"


# ===========================================================================
# Decision function — reuses Policy Engine / approval state, never bypasses it
# ===========================================================================
def test_decide_communication_blocked_when_policy_rejected(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    from models.payment import Payment
    payment = db_session.query(Payment).filter_by(id=case.payment_id).first()
    payment.status = "unknown"
    db_session.commit()
    execute_action(db_session, action.id)   # -> BLOCKED / POLICY_REJECTED
    db_session.refresh(action)

    from models.case_intelligence import CaseIntelligence
    intel = db_session.query(CaseIntelligence).filter_by(recovery_case_id=case.id).order_by(
        CaseIntelligence.version.desc()).first()
    # The stored intelligence verdict from ANALYSIS time may still say APPROVED
    # (tamper happened after analysis) — decide_communication must still see
    # today's REJECTED reality via the action, for link-bearing types.
    decision = decide_communication("PAYMENT_LINK_CREATED", case=case, action=action, intelligence=intel)
    assert decision.eligible is False


def test_decide_communication_requires_approval(db_session, razorpay_env):
    payload = upi_timeout_payload()
    payload["payload"]["payment"]["entity"]["amount"] = 1499900
    payload["payload"]["payment"]["entity"]["method"] = "card"
    payload["payload"]["payment"]["entity"]["error_code"] = "GATEWAY_ERROR"
    payload["payload"]["payment"]["entity"]["error_description"] = "Transaction declined: insufficient funds / limit exceeded"
    case = _analyzed_case(db_session, payload)
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)   # -> BLOCKED / NEEDS_APPROVAL
    db_session.refresh(action)

    decision = decide_communication("PAYMENT_LINK_CREATED", case=case, action=action, intelligence=None)
    assert decision.eligible is False
    assert decision.skipped_reason == "REQUIRES_APPROVAL"


def test_decide_communication_eligible_once_executed(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    db_session.refresh(action)
    decision = decide_communication("PAYMENT_LINK_CREATED", case=case, action=action, intelligence=None)
    assert decision.eligible is True


def test_decide_communication_payment_recovered_requires_verified_outcome(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    db_session.refresh(action)
    not_yet = decide_communication("PAYMENT_RECOVERED", case=case, action=action, intelligence=None)
    assert not_yet.eligible is False
    action.outcome = "RECOVERED"
    db_session.commit()
    now_eligible = decide_communication("PAYMENT_RECOVERED", case=case, action=action, intelligence=None)
    assert now_eligible.eligible is True


# ===========================================================================
# send_communication — contact info, opt-out, duplicates, rate limiting, audit
# ===========================================================================
def test_send_skips_with_no_contact_info(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    from models.customer import Customer
    customer = db_session.query(Customer).filter_by(id=case.customer_id).first()
    customer.email = None
    db_session.commit()

    result = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                                channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    assert result.status == "SKIPPED"
    assert result.skipped_reason == "NO_CONTACT_INFO"


def test_send_succeeds_and_writes_audit(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    result = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                                channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    assert result.status == "SENT"
    assert result.provider == "FAKE_EMAIL"
    assert result.sent_at is not None

    events = {a.action for a in db_session.query(AuditLog).filter(
        AuditLog.recovery_case_id == case.id, AuditLog.actor == "COMMUNICATION_ENGINE").all()}
    assert "COMMUNICATION_SENT" in events


def test_duplicate_communication_prevented(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    first = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                               channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    assert first.status == "SENT"
    second = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                                channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    assert second.status == "SKIPPED"
    assert second.skipped_reason == "DUPLICATE"

    total = db_session.query(Communication).filter_by(recovery_case_id=case.id).count()
    assert total == 2   # one SENT, one SKIPPED — never silently merged/lost


def test_opt_out_respected(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    from models.customer import Customer
    customer = db_session.query(Customer).filter_by(id=case.customer_id).first()
    customer.opted_out_channels = "EMAIL,SMS"
    db_session.commit()

    result = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                                channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    assert result.status == "OPTED_OUT"

    # WhatsApp was not opted out — still sendable (uses the same phone number).
    still_ok = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                                  channel="WHATSAPP", message_type="PAYMENT_LINK_CREATED")
    assert still_ok.status == "SENT"


def test_rate_limiting_per_case(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "COMMUNICATION_RATE_LIMIT_PER_CASE_PER_DAY", 2)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    # Two distinct message types so duplicate-prevention doesn't also fire.
    r1 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    r2 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="SMS", message_type="RECOVERY_REMINDER")
    r3 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="WHATSAPP", message_type="PAYMENT_RECOVERY")
    assert r1.status == "SENT" and r2.status == "SENT"
    assert r3.status == "SKIPPED"
    assert r3.skipped_reason == "RATE_LIMITED"


def test_communication_recorded_as_failed_not_sent_when_provider_fails(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "SMTP_HOST", "")   # not configured -> provider fails
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    result = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                                channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    assert result.status == "FAILED"
    assert result.status != "SENT"
    assert result.error_code == "NOT_CONFIGURED"

    events = {a.action for a in db_session.query(AuditLog).filter(
        AuditLog.recovery_case_id == case.id, AuditLog.actor == "COMMUNICATION_ENGINE").all()}
    assert "COMMUNICATION_FAILED" in events
    assert "COMMUNICATION_SENT" not in events


# ===========================================================================
# End-to-end via the real HTTP endpoint (auth + role gating already covered
# in test_rbac.py / test_organization_isolation.py)
# ===========================================================================
def test_send_endpoint_full_flow(client, razorpay_env):
    from test_actions import _api_analyzed_case, _api_propose, _api_execute
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])

    res = client.post(f"/api/v1/recovery-cases/{cn}/communications/send", json={
        "channel": "EMAIL", "message_type": "PAYMENT_LINK_CREATED",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["communication"]["status"] == "SENT"
    assert body["communication"]["provider"] == "FAKE_EMAIL"

    history = client.get(f"/api/v1/recovery-cases/{cn}/communications").json()
    assert history["total"] == 1
    assert history["items"][0]["message_type"] == "PAYMENT_LINK_CREATED"
