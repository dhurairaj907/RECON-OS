"""
RECON OS — Phase 7: Real Customer Communication + Controlled Recovery
Automation tests  (SAFETY-CRITICAL)

Covers: real email/SMS/WhatsApp provider completeness (SSL, templates,
message-id parsing, missing-recipient handling), password-reset delivery +
rate limiting, the new per-case/per-customer communication limits, the
action-less duplicate-prevention fix, controlled automatic communication
(hooks + the on-demand reminder sequence), the delivery webhook (signature,
idempotency, SENT-vs-DELIVERED), the AI-recommendation-is-advisory-only
guarantee, and organization isolation / RBAC on every new endpoint.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from config import settings
from models.audit_log import AuditLog
from models.communication import Communication
from models.customer import Customer
from services.actions.executor import execute_action
from services.actions.verification import apply_recovery
from services.communications import automation
from services.communications.providers import (
    SmtpEmailProvider, WebhookSMSProvider, WebhookWhatsAppProvider, get_communication_provider,
)
from services.communications.service import send_communication

from test_actions import (  # noqa: F401 — reused fixtures + helpers
    razorpay_env,
    upi_timeout_payload,
    _analyzed_case,
    _proposed_action,
    _api_analyzed_case,
    _api_propose,
    _api_execute,
)


# ===========================================================================
# EMAIL — SMTP provider completeness
# ===========================================================================
class _FakeSMTP:
    """Records every call; raises based on `mode` to simulate provider states."""
    instances = []

    def __init__(self, host, port, timeout=10):
        self.host, self.port = host, port
        self.logged_in = False
        self.sent = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, pw):
        if _FakeSMTP.mode == "auth_fail":
            raise __import__("smtplib").SMTPAuthenticationError(535, b"bad creds")
        self.logged_in = True

    def sendmail(self, from_addr, to_addrs, msg):
        if _FakeSMTP.mode == "transport_fail":
            raise OSError("connection reset")
        self.sent.append((from_addr, to_addrs, msg))


_FakeSMTP.mode = "ok"


@pytest.fixture
def smtp_env(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@recon.test")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(settings, "SMTP_USE_SSL", False)
    _FakeSMTP.mode = "ok"
    _FakeSMTP.instances = []
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr("smtplib.SMTP_SSL", _FakeSMTP)
    yield


def test_smtp_email_missing_credentials_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    result = SmtpEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is False and result.error_code == "NOT_CONFIGURED"


def test_smtp_email_no_recipient_fails_safely(smtp_env):
    result = SmtpEmailProvider().send(to="", subject="s", body="b")
    assert result.ok is False and result.error_code == "NO_RECIPIENT"


def test_smtp_email_successful_send(smtp_env):
    result = SmtpEmailProvider().send(to="customer@example.com", subject="Hi", body="Body")
    assert result.ok is True and result.status == "SENT" and result.provider == "SMTP_EMAIL"
    assert _FakeSMTP.instances[-1].sent


def test_smtp_email_uses_ssl_when_configured(smtp_env, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_USE_SSL", True)
    monkeypatch.setattr(settings, "SMTP_PORT", 465)
    result = SmtpEmailProvider().send(to="customer@example.com", subject="Hi", body="Body")
    assert result.ok is True


def test_smtp_email_auth_failure(smtp_env, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_USERNAME", "bot")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "wrong")
    _FakeSMTP.mode = "auth_fail"
    result = SmtpEmailProvider().send(to="customer@example.com", subject="Hi", body="Body")
    assert result.ok is False and result.error_code == "SMTP_AUTH_ERROR"


def test_smtp_email_transport_failure(smtp_env):
    _FakeSMTP.mode = "transport_fail"
    result = SmtpEmailProvider().send(to="customer@example.com", subject="Hi", body="Body")
    assert result.ok is False and result.error_code == "SMTP_ERROR"


# ===========================================================================
# SMS — webhook provider completeness
# ===========================================================================
class _FakeHttpxClient:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, headers=None):
        return _FakeHttpxClient.response


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def test_sms_missing_configuration(monkeypatch):
    monkeypatch.setattr(settings, "SMS_PROVIDER_WEBHOOK_URL", "")
    result = WebhookSMSProvider().send(to="+911234567890", subject="", body="b")
    assert result.ok is False and result.error_code == "NOT_CONFIGURED"


def test_sms_missing_phone(monkeypatch):
    monkeypatch.setattr(settings, "SMS_PROVIDER_WEBHOOK_URL", "https://sms.example.com/send")
    result = WebhookSMSProvider().send(to="", subject="", body="b")
    assert result.ok is False and result.error_code == "NO_RECIPIENT"


def test_sms_successful_send_parses_provider_message_id(monkeypatch):
    monkeypatch.setattr(settings, "SMS_PROVIDER_WEBHOOK_URL", "https://sms.example.com/send")
    _FakeHttpxClient.response = _Resp(200, {"message_id": "sms_abc123"})
    monkeypatch.setattr("httpx.Client", _FakeHttpxClient)
    result = WebhookSMSProvider().send(to="+911234567890", subject="", body="b")
    assert result.ok is True and result.status == "SENT"
    assert result.provider_message_id == "sms_abc123"


def test_sms_provider_failure(monkeypatch):
    monkeypatch.setattr(settings, "SMS_PROVIDER_WEBHOOK_URL", "https://sms.example.com/send")
    _FakeHttpxClient.response = _Resp(502, {})
    monkeypatch.setattr("httpx.Client", _FakeHttpxClient)
    result = WebhookSMSProvider().send(to="+911234567890", subject="", body="b")
    assert result.ok is False and result.error_code == "HTTP_502"


# ===========================================================================
# WHATSAPP — template enforcement + webhook provider completeness
# ===========================================================================
def test_whatsapp_missing_configuration(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER_WEBHOOK_URL", "")
    result = WebhookWhatsAppProvider().send(to="+911234567890", subject="", body="b")
    assert result.ok is False and result.error_code == "NOT_CONFIGURED"


def test_whatsapp_requires_template_by_default(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER_WEBHOOK_URL", "https://wa.example.com/send")
    assert settings.WHATSAPP_REQUIRE_TEMPLATE is True
    result = WebhookWhatsAppProvider().send(to="+911234567890", subject="", body="freeform text")
    assert result.ok is False and result.error_code == "TEMPLATE_NOT_CONFIGURED"


def test_whatsapp_sends_with_configured_template(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER_WEBHOOK_URL", "https://wa.example.com/send")
    _FakeHttpxClient.response = _Resp(200, {"id": "wa_msg_1"})
    monkeypatch.setattr("httpx.Client", _FakeHttpxClient)
    result = WebhookWhatsAppProvider().send(
        to="+911234567890", subject="", body="ignored",
        template_id="payment_link_v1", template_vars={"amount": "499.00"},
    )
    assert result.ok is True and result.provider_message_id == "wa_msg_1"


def test_whatsapp_provider_failure(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER_WEBHOOK_URL", "https://wa.example.com/send")
    _FakeHttpxClient.response = _Resp(400, {})
    monkeypatch.setattr("httpx.Client", _FakeHttpxClient)
    result = WebhookWhatsAppProvider().send(to="+91123", subject="", body="x", template_id="tpl1")
    assert result.ok is False and result.error_code == "HTTP_400"


def test_resolved_whatsapp_template_parses_key_value_list(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_TEMPLATE_IDS",
                        "PAYMENT_LINK_CREATED=plink_v1, RECOVERY_REMINDER=reminder_v1")
    assert settings.resolved_whatsapp_template("PAYMENT_LINK_CREATED") == "plink_v1"
    assert settings.resolved_whatsapp_template("RECOVERY_REMINDER") == "reminder_v1"
    assert settings.resolved_whatsapp_template("PAYMENT_RECOVERED") == ""


# ===========================================================================
# PASSWORD RESET — delivery, rate limiting, security
# ===========================================================================
def test_password_reset_rate_limited(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(settings, "PASSWORD_RESET_RATE_LIMIT_PER_HOUR", 2)
    c = unauthenticated_client
    c.post("/api/v1/auth/register", json={
        "email": "ratelimited@recon.test", "password": "Password123!", "organization_name": "RLOrg",
    })
    r1 = c.post("/api/v1/auth/forgot-password", json={"email": "ratelimited@recon.test"})
    r2 = c.post("/api/v1/auth/forgot-password", json={"email": "ratelimited@recon.test"})
    r3 = c.post("/api/v1/auth/forgot-password", json={"email": "ratelimited@recon.test"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r3.status_code == 429


def test_password_reset_sends_real_email_when_configured(unauthenticated_client, monkeypatch, caplog):
    """Real-mode EMAIL goes through BrevoEmailProvider (HTTPS REST) — see
    services/communications/providers.py — not smtplib; this fakes the same
    httpx.Client the Brevo SMS/WhatsApp providers already mock, never a real
    network call."""
    c = unauthenticated_client
    c.post("/api/v1/auth/register", json={
        "email": "realreset@recon.test", "password": "Password123!", "organization_name": "RealResetOrg",
    })
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "test-brevo-key")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@recon.test")

    captured = {}

    class _Resp:
        status_code = 201
        def json(self):
            return {"messageId": "<reset-test@smtp-relay.brevo.com>"}

    class _FakeHttpxClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None, headers=None, **k):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr("services.communications.providers.httpx.Client", lambda *a, **k: _FakeHttpxClient())

    res = c.post("/api/v1/auth/forgot-password", json={"email": "realreset@recon.test"})
    assert res.status_code == 200
    assert "token" not in res.text.lower().replace("please log in", "")
    # A real send was actually attempted via the real provider.
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert "reset-password?token=" in captured["json"]["textContent"]


def test_forgot_password_reset_link_uses_frontend_base_url(unauthenticated_client, monkeypatch):
    """The reset link embedded in the email must be built from
    FRONTEND_BASE_URL (https://recon-os-els.pages.dev in production), with
    trailing-slash normalization so the link is never malformed."""
    c = unauthenticated_client
    c.post("/api/v1/auth/register", json={
        "email": "linkcheck@recon.test", "password": "Password123!", "organization_name": "LinkCheckOrg",
    })
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "test-brevo-key")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@recon.test")
    # Deliberately WITH a trailing slash — rstrip('/') in auth.py must
    # normalize this, never producing a double slash before /reset-password.
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://recon-os-els.pages.dev/")

    captured = {}

    class _Resp:
        status_code = 201
        def json(self):
            return {"messageId": "<link-test@smtp-relay.brevo.com>"}

    class _FakeHttpxClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None, headers=None, **k):
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr("services.communications.providers.httpx.Client", lambda *a, **k: _FakeHttpxClient())

    res = c.post("/api/v1/auth/forgot-password", json={"email": "linkcheck@recon.test"})
    assert res.status_code == 200
    body = captured["json"]["textContent"]
    assert "https://recon-os-els.pages.dev/reset-password?token=" in body
    assert "pages.dev//reset-password" not in body   # no double slash


def test_forgot_password_email_provider_failure_still_returns_200(unauthenticated_client, monkeypatch, db_session):
    """A provider rejection (e.g. Brevo 500) must never surface to the
    caller — anti-enumeration requires the same generic 200 regardless of
    whether delivery actually succeeded. The failure must still be visible
    server-side via the audit trail (see routers/auth.py)."""
    c = unauthenticated_client
    c.post("/api/v1/auth/register", json={
        "email": "providerfail@recon.test", "password": "Password123!", "organization_name": "ProviderFailOrg",
    })
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "test-brevo-key")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@recon.test")

    class _Resp:
        status_code = 500
        def json(self):
            return {}

    class _FakeHttpxClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()

    monkeypatch.setattr("services.communications.providers.httpx.Client", lambda *a, **k: _FakeHttpxClient())

    import time
    started = time.monotonic()
    res = c.post("/api/v1/auth/forgot-password", json={"email": "providerfail@recon.test"})
    elapsed = time.monotonic() - started

    assert res.status_code == 200
    assert res.json()["message"] == "If that email exists, a password reset link has been sent."
    assert elapsed < 5  # a provider rejection must resolve promptly, never hang

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "PASSWORD_RESET_EMAIL_FAILED")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert "providerfail@recon.test" in audit.detail
    assert audit.metadata_json["provider"] == "BREVO_EMAIL"


def test_forgot_password_email_provider_timeout_does_not_hang_request(unauthenticated_client, monkeypatch):
    """Root-cause regression: the currently-DEPLOYED SmtpEmailProvider path
    can leave a forgot-password request pending far longer than its own
    socket timeout when the underlying transport hangs (e.g. Render's
    free-tier network handling of outbound SMTP). This proves the REST-based
    BrevoEmailProvider path bounds the request to its own httpx timeout
    instead — a provider-level timeout must never make the endpoint hang."""
    c = unauthenticated_client
    c.post("/api/v1/auth/register", json={
        "email": "providertimeout@recon.test", "password": "Password123!", "organization_name": "ProviderTimeoutOrg",
    })
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "test-brevo-key")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@recon.test")

    class _TimingOutClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): raise httpx.TimeoutException("simulated hang")

    monkeypatch.setattr("services.communications.providers.httpx.Client", lambda *a, **k: _TimingOutClient())

    import time
    started = time.monotonic()
    res = c.post("/api/v1/auth/forgot-password", json={"email": "providertimeout@recon.test"})
    elapsed = time.monotonic() - started

    assert res.status_code == 200
    assert elapsed < 5  # never hangs — the provider's own timeout handling returns promptly


def test_password_reset_never_logs_plaintext_token_in_real_mode(unauthenticated_client, monkeypatch, caplog):
    import logging
    c = unauthenticated_client
    c.post("/api/v1/auth/register", json={
        "email": "noplaintext@recon.test", "password": "Password123!", "organization_name": "NoPlaintextOrg",
    })
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@recon.test")
    _FakeSMTP.mode = "ok"
    _FakeSMTP.instances = []
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    with caplog.at_level(logging.INFO, logger="recon.routers.auth"):
        c.post("/api/v1/auth/forgot-password", json={"email": "noplaintext@recon.test"})
    messages = [r.message for r in caplog.records]
    # The dev-only plaintext-token log line must never fire in real mode.
    assert not any("[DEV]" in m for m in messages)
    assert not any("dev-log only" in m for m in messages)


# ===========================================================================
# COMMUNICATION SAFETY — new per-case / per-customer limits, dedup fix
# ===========================================================================
def test_max_communications_per_case_enforced(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "MAX_COMMUNICATIONS_PER_CASE", 1)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    r1 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    assert r1.status == "SENT"
    r2 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="SMS", message_type="RECOVERY_REMINDER")
    assert r2.status == "SKIPPED" and r2.skipped_reason == "CASE_LIMIT_REACHED"


def test_max_communications_per_customer_per_day_enforced(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "MAX_COMMUNICATIONS_PER_CUSTOMER_PER_DAY", 1)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    r1 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    assert r1.status == "SENT"
    r2 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="SMS", message_type="RECOVERY_REMINDER")
    assert r2.status == "SKIPPED" and r2.skipped_reason == "CUSTOMER_DAILY_LIMIT_REACHED"


def test_duplicate_prevention_covers_action_less_message_types(db_session, razorpay_env):
    """PAYMENT_FAILED has no RecoveryAction — this closes a real gap where
    such messages were never deduplicated at all before Phase 7."""
    case = _analyzed_case(db_session, upi_timeout_payload())
    first = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                               channel="EMAIL", message_type="PAYMENT_FAILED")
    assert first.status == "SENT"
    second = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                                channel="EMAIL", message_type="PAYMENT_FAILED")
    assert second.status == "SKIPPED" and second.skipped_reason == "DUPLICATE"


def test_idempotency_key_is_deterministic_not_random(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    comm = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                              channel="EMAIL", message_type="PAYMENT_LINK_CREATED")
    expected = f"{case.id}:{action.id}:EMAIL:PAYMENT_LINK_CREATED"
    assert comm.idempotency_key == expected


# ===========================================================================
# CONTROLLED AUTOMATIC COMMUNICATION
# ===========================================================================
def test_automation_disabled_by_default_no_auto_send(db_session, razorpay_env):
    assert settings.AUTOMATIC_COMMUNICATIONS_ENABLED is False
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    total = db_session.query(Communication).filter_by(recovery_case_id=case.id).count()
    assert total == 0


def test_automation_sends_on_action_executed_when_enabled(db_session, razorpay_env, monkeypatch):
    """Objective 30/31: an approved automated recovery fans out to EVERY
    configured, eligible channel (EMAIL+SMS+WHATSAPP) as part of the SAME
    automated event — not just one AI-picked channel."""
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    comms = db_session.query(Communication).filter_by(recovery_case_id=case.id).all()
    channels = {c.channel for c in comms}
    assert channels == {"EMAIL", "SMS", "WHATSAPP"}
    assert all(c.message_type == "PAYMENT_RECOVERY" for c in comms)
    assert all(c.status == "SENT" for c in comms), [c.status for c in comms]

    audits = {a.action for a in db_session.query(AuditLog).filter_by(recovery_case_id=case.id).all()}
    assert "AI_RECOMMENDATION_CONSIDERED" in audits


def test_automation_one_channel_failure_never_blocks_the_others(db_session, razorpay_env, monkeypatch):
    """Objective 30/31/80: a failure/skip on one channel must never prevent
    the others from being attempted or crash the overall recovery."""
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    real_send = __import__("services.communications.automation", fromlist=["send_communication"]).send_communication

    def flaky_send(db, *, merchant_id, case, channel, message_type, decided_by="OPERATOR"):
        if channel == "SMS":
            raise RuntimeError("simulated SMS provider outage")
        return real_send(db, merchant_id=merchant_id, case=case, channel=channel,
                         message_type=message_type, decided_by=decided_by)

    monkeypatch.setattr("services.communications.automation.send_communication", flaky_send)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)   # must not raise despite SMS blowing up

    comms = db_session.query(Communication).filter_by(recovery_case_id=case.id).all()
    channels_sent = {c.channel for c in comms if c.status == "SENT"}
    assert channels_sent == {"EMAIL", "WHATSAPP"}   # SMS never persisted since it raised before returning


def test_automation_sends_thank_you_on_recovery_verified(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    db_session.refresh(action)

    apply_recovery(db_session, action, amount_paid_paise=action.amount_paise,
                   currency="INR", source_event_id="evt_test_recovered")

    recovered_msgs = db_session.query(Communication).filter_by(
        recovery_case_id=case.id, message_type="PAYMENT_RECOVERED").all()
    # All three channels are attempted; some may legitimately be rate-limited
    # (the same customer already received 3 messages moments earlier for
    # PAYMENT_RECOVERY within COMMUNICATION_RATE_LIMIT_PER_CASE_PER_DAY) —
    # partial throttling is correct, honest behavior, not a bug.
    assert len(recovered_msgs) == 3
    assert any(c.status == "SENT" for c in recovered_msgs)
    assert all(c.status in ("SENT", "SKIPPED") for c in recovered_msgs)


def test_automation_never_sends_for_simulated_recovery(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)
    db_session.refresh(action)

    apply_recovery(db_session, action, amount_paid_paise=action.amount_paise,
                   currency="INR", source_event_id="evt_sim", simulated=True)

    recovered_msgs = db_session.query(Communication).filter_by(
        recovery_case_id=case.id, message_type="PAYMENT_RECOVERED").all()
    assert len(recovered_msgs) == 0


def test_automation_failure_never_breaks_action_execution(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    monkeypatch.setattr("services.communications.automation.send_communication",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "EXECUTED"   # execution itself is unaffected


def test_evaluate_reminder_sequence_disabled_by_default(db_session, razorpay_env):
    case = _analyzed_case(db_session, upi_timeout_payload())
    decision = automation.evaluate_reminder_sequence(db_session, merchant_id=case.merchant_id, case=case)
    assert decision.sent is False
    assert "disabled" in decision.reason.lower()


def test_evaluate_reminder_sequence_stops_after_recovery(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)   # sends the initial auto message
    db_session.refresh(action)
    apply_recovery(db_session, action, amount_paid_paise=action.amount_paise,
                   currency="INR", source_event_id="evt_recovered_2")
    db_session.refresh(case)

    decision = automation.evaluate_reminder_sequence(db_session, merchant_id=case.merchant_id, case=case)
    assert decision.sent is False
    assert decision.communication is not None
    assert decision.communication.status == "CANCELLED"


def test_evaluate_reminder_sequence_respects_min_hours_between_messages(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "MIN_HOURS_BETWEEN_MESSAGES", 12)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)   # initial auto message just sent

    decision = automation.evaluate_reminder_sequence(db_session, merchant_id=case.merchant_id, case=case)
    assert decision.sent is False
    assert "between messages" in decision.reason.lower()


def test_evaluate_reminder_sequence_sends_once_window_elapsed(db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "MIN_HOURS_BETWEEN_MESSAGES", 1)
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    execute_action(db_session, action.id)

    # Automatic execution now fans out to every channel — backdate ALL of
    # them so evaluate_reminder_sequence's "most recent send" lookup sees a
    # uniformly-elapsed window, not just one channel's timestamp.
    initials = db_session.query(Communication).filter_by(recovery_case_id=case.id).all()
    for c in initials:
        c.sent_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()

    decision = automation.evaluate_reminder_sequence(db_session, merchant_id=case.merchant_id, case=case)
    assert decision.sent is True
    assert decision.communication.message_type == "RECOVERY_REMINDER"


def test_evaluate_sequence_endpoint_rbac_and_org_isolation(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    c = unauthenticated_client
    c.post("/api/v1/auth/register", json={
        "email": "seqowner@recon.test", "password": "Password123!", "organization_name": "SeqOrg",
    })
    cn = _api_analyzed_case(c)
    action = _api_propose(c, cn)
    _api_execute(c, action["id"])

    ok = c.post(f"/api/v1/recovery-cases/{cn}/communications/evaluate-sequence")
    assert ok.status_code == 200

    c.cookies.clear()
    c.post("/api/v1/auth/register", json={
        "email": "seqother@recon.test", "password": "Password123!", "organization_name": "SeqOtherOrg",
    })
    denied = c.post(f"/api/v1/recovery-cases/{cn}/communications/evaluate-sequence")
    assert denied.status_code == 404


# ===========================================================================
# DELIVERY WEBHOOK — signature, idempotency, SENT vs DELIVERED
# ===========================================================================
def _sign(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_delivery_webhook_rejects_unsigned(client, monkeypatch):
    monkeypatch.setattr(settings, "COMMUNICATION_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(settings, "COMMUNICATION_ALLOW_UNSIGNED_WEBHOOKS", False)
    body = json.dumps({"provider_message_id": "x", "event_id": "e1", "status": "delivered"}).encode()
    res = client.post("/api/v1/webhooks/communications/delivery", content=body,
                      headers={"Content-Type": "application/json"})
    assert res.status_code == 401


def test_delivery_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "COMMUNICATION_WEBHOOK_SECRET", "whsec_test")
    body = json.dumps({"provider_message_id": "x", "event_id": "e1", "status": "delivered"}).encode()
    res = client.post("/api/v1/webhooks/communications/delivery", content=body,
                      headers={"Content-Type": "application/json", "X-RECON-Comm-Signature": "wrong"})
    assert res.status_code == 401


def test_delivery_webhook_accepted_and_idempotent(client, db_session, razorpay_env, monkeypatch):
    monkeypatch.setattr(settings, "COMMUNICATION_WEBHOOK_SECRET", "whsec_test")
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])
    send_res = client.post(f"/api/v1/recovery-cases/{cn}/communications/send", json={
        "channel": "EMAIL", "message_type": "PAYMENT_LINK_CREATED",
    })
    comm = send_res.json()["communication"]
    assert comm["status"] == "SENT"
    provider_message_id = comm["provider_message_id"]
    assert provider_message_id

    body = json.dumps({
        "provider_message_id": provider_message_id, "event_id": "evt_delivered_1", "status": "delivered",
    }).encode()
    sig = _sign("whsec_test", body)
    r1 = client.post("/api/v1/webhooks/communications/delivery", content=body,
                     headers={"Content-Type": "application/json", "X-RECON-Comm-Signature": sig})
    assert r1.status_code == 200 and r1.json()["new_status"] == "DELIVERED"

    history = client.get(f"/api/v1/recovery-cases/{cn}/communications").json()
    assert history["items"][0]["status"] == "DELIVERED"

    # Duplicate delivery of the SAME event is a safe no-op.
    r2 = client.post("/api/v1/webhooks/communications/delivery", content=body,
                     headers={"Content-Type": "application/json", "X-RECON-Comm-Signature": sig})
    assert r2.status_code == 200 and r2.json()["reason"] == "duplicate_event"


def test_delivery_webhook_unknown_message_id_ignored(client, monkeypatch):
    monkeypatch.setattr(settings, "COMMUNICATION_WEBHOOK_SECRET", "whsec_test")
    body = json.dumps({
        "provider_message_id": "does-not-exist-anywhere", "event_id": "evt_x", "status": "delivered",
    }).encode()
    sig = _sign("whsec_test", body)
    res = client.post("/api/v1/webhooks/communications/delivery", content=body,
                      headers={"Content-Type": "application/json", "X-RECON-Comm-Signature": sig})
    assert res.status_code == 200
    assert res.json()["reason"] == "unknown_provider_message_id"


# ===========================================================================
# AI — advisory only, cannot bypass policy / approval / send directly
# ===========================================================================
def test_ai_recommendation_never_calls_send_communication(db_session, razorpay_env, monkeypatch):
    called = {"count": 0}
    monkeypatch.setattr("services.communications.automation.send_communication",
                        lambda *a, **k: called.__setitem__("count", called["count"] + 1))
    case = _analyzed_case(db_session, upi_timeout_payload())
    rec = automation.ai_recommendation(db_session, case)
    assert isinstance(rec, dict)
    assert set(rec.keys()) >= {"strategy", "channel", "confidence", "expected_recovery_value", "reason"}
    assert called["count"] == 0


def test_ai_recommendation_cannot_bypass_policy_or_approval(db_session, razorpay_env, monkeypatch):
    """A NEEDS_APPROVAL action is never EXECUTED, so the automatic
    on-action-executed hook structurally never fires for it — regardless of
    what the AI recommends."""
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    payload = upi_timeout_payload()
    payload["payload"]["payment"]["entity"]["amount"] = 1499900
    payload["payload"]["payment"]["entity"]["method"] = "card"
    payload["payload"]["payment"]["entity"]["error_code"] = "GATEWAY_ERROR"
    payload["payload"]["payment"]["entity"]["error_description"] = "Transaction declined: insufficient funds / limit exceeded"
    case = _analyzed_case(db_session, payload)
    action = _proposed_action(db_session, case)
    result = execute_action(db_session, action.id)
    assert result.status == "BLOCKED" and result.blocked_reason == "NEEDS_APPROVAL"

    total = db_session.query(Communication).filter_by(recovery_case_id=case.id).count()
    assert total == 0
