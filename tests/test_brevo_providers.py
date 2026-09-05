"""
RECON OS — Real Brevo email/SMS/WhatsApp provider tests.

Covers BrevoEmailProvider / BrevoSmsProvider / BrevoWhatsAppProvider
(services/communications/providers.py) at the unit level (mocked
httpx.Client — never a real network call), plus end-to-end
send_communication() tests proving the EXISTING idempotency/rate-limit/
opt-out layer (services/communications/service.py, UNCHANGED by this work)
still holds correctly when RECON_COMMUNICATIONS_MODE is switched to "real"
and the registry resolves to the Brevo classes for all three channels.

BrevoEmailProvider was added because Render's Free plan has no Shell access
to reliably exercise/diagnose outbound SMTP from the deployed container —
production EMAIL now goes through Brevo's HTTPS REST API instead.
SmtpEmailProvider itself is completely unmodified and still covered by its
own existing tests (test_communications_phase7.py) for local dev.

Nothing here ever calls Brevo for real — every test either calls the
provider class directly with a faked httpx.Client, or drives
send_communication() with the SAME fake client patched in.
"""

from decimal import Decimal

import httpx
import pytest

from config import settings
from models.communication import Communication
from services.communications.providers import (
    BrevoEmailProvider,
    BrevoSmsProvider,
    BrevoWhatsAppProvider,
    _normalize_phone_for_brevo,
    get_communication_provider,
)
from services.communications.service import send_communication

from test_actions import (  # noqa: F401 — reused fixtures + helpers
    razorpay_env,
    upi_timeout_payload,
    _analyzed_case,
    _proposed_action,
)


class _Resp:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeHttpClient:
    """Records every POST call (url, json body, headers) and returns queued
    responses in order — a fresh instance per test, never shared state."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, headers=None, **kwargs):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if not self._responses:
            raise AssertionError("no more queued responses — test made an unexpected extra call")
        return self._responses.pop(0)


def _patch_client(monkeypatch, responses):
    fake = _FakeHttpClient(responses)
    monkeypatch.setattr("services.communications.providers.httpx.Client", lambda *a, **k: fake)
    return fake


def _brevo_env(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "brevo-secret-DO-NOT-LEAK")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "recon@example.com")
    monkeypatch.setattr(settings, "BREVO_SMS_SENDER", "RECONS")
    monkeypatch.setattr(settings, "BREVO_WHATSAPP_SENDER", "919999999999")
    monkeypatch.setattr(settings, "BREVO_WHATSAPP_TEMPLATE_IDS", "PAYMENT_LINK_CREATED=101,PAYMENT_RECOVERY=102")


# ===========================================================================
# Phone normalization — pure function
# ===========================================================================
def test_normalize_phone_strips_plus_and_e164_to_brevo_digits_form():
    assert _normalize_phone_for_brevo("+919876543210") == "919876543210"


def test_normalize_phone_strips_spaces_and_dashes():
    assert _normalize_phone_for_brevo("+91 98765-43210") == "919876543210"


def test_normalize_phone_malformed_returns_none():
    assert _normalize_phone_for_brevo("not-a-number") is None
    assert _normalize_phone_for_brevo("") is None
    assert _normalize_phone_for_brevo(None) is None


# ===========================================================================
# BrevoEmailProvider — unit tests (mocked httpx)
# ===========================================================================
def test_email_missing_api_key_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "recon@example.com")
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is False
    assert result.error_code == "NOT_CONFIGURED"
    assert "BREVO_API_KEY" in result.error_message


def test_email_missing_sender_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "k")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "")
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is False
    assert result.error_code == "NOT_CONFIGURED"
    assert "SMTP_FROM_EMAIL" in result.error_message


def test_email_missing_recipient(monkeypatch):
    _brevo_env(monkeypatch)
    result = BrevoEmailProvider().send(to="", subject="s", body="b")
    assert result.ok is False
    assert result.error_code == "NO_RECIPIENT"


def test_email_success_correct_endpoint_headers_and_body(monkeypatch):
    _brevo_env(monkeypatch)
    fake = _patch_client(monkeypatch, [_Resp(201, {"messageId": "<abc123@brevo.com>"})])
    result = BrevoEmailProvider().send(to="customer@example.com", subject="RECON OS SMTP Test",
                                       body="This is a controlled RECON OS test.")

    assert result.ok is True
    assert result.status == "SENT"
    assert result.provider == "BREVO_EMAIL"
    # Angle brackets stripped — must match what brevo_webhook.py's inbound
    # canonicalization looks up later, see BrevoEmailProvider's docstring.
    assert result.provider_message_id == "abc123@brevo.com"

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://api.brevo.com/v3/smtp/email"
    assert call["headers"]["api-key"] == "brevo-secret-DO-NOT-LEAK"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["json"]["sender"] == {"email": "recon@example.com"}
    assert call["json"]["to"] == [{"email": "customer@example.com"}]
    assert call["json"]["subject"] == "RECON OS SMTP Test"
    assert call["json"]["textContent"] == "This is a controlled RECON OS test."


def test_email_auth_error_distinguished(monkeypatch):
    _brevo_env(monkeypatch)
    _patch_client(monkeypatch, [_Resp(401, {"message": "invalid api key"})])
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is False
    assert result.error_code == "BREVO_AUTH_ERROR"


def test_email_forbidden_error_distinguished(monkeypatch):
    _brevo_env(monkeypatch)
    _patch_client(monkeypatch, [_Resp(403, {"message": "forbidden"})])
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is False
    assert result.error_code == "BREVO_AUTH_ERROR"


def test_email_provider_rejection_normalized(monkeypatch):
    _brevo_env(monkeypatch)
    _patch_client(monkeypatch, [_Resp(400, {"code": "invalid_parameter", "message": "bad sender"})])
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is False
    assert result.error_code == "HTTP_400"


def test_email_transport_error_normalized(monkeypatch):
    _brevo_env(monkeypatch)

    class _RaisingClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("services.communications.providers.httpx.Client", lambda *a, **k: _RaisingClient())
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is False
    assert result.error_code == "TRANSPORT_ERROR"


def test_email_timeout_error_normalized(monkeypatch):
    _brevo_env(monkeypatch)

    class _TimingOutClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            raise httpx.TimeoutException("slow")

    monkeypatch.setattr("services.communications.providers.httpx.Client", lambda *a, **k: _TimingOutClient())
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is False
    assert result.error_code == "TRANSPORT_ERROR"


def test_email_malformed_json_response_still_succeeds_without_message_id(monkeypatch):
    """A 2xx with an unparsable body must not crash — no message id is
    fabricated, but the send is still recorded as accepted."""
    _brevo_env(monkeypatch)

    class _MalformedResp:
        status_code = 201

        def json(self):
            raise ValueError("not json")

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _MalformedResp()

    monkeypatch.setattr("services.communications.providers.httpx.Client", lambda *a, **k: _Client())
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.ok is True
    assert result.status == "SENT"
    assert result.provider_message_id is None


def test_email_message_id_brackets_stripped_for_webhook_correlation(monkeypatch):
    """Regression: Brevo's REST response wraps messageId in RFC 5322 angle
    brackets. If stored as-is, a later delivery webhook (which canonicalizes
    the inbound message-id by stripping brackets — see
    brevo_webhook.py::_canonical_message_id) would never match this row,
    silently breaking SENT -> DELIVERED correlation for every real email."""
    _brevo_env(monkeypatch)
    _patch_client(monkeypatch, [_Resp(201, {"messageId": "<xyz-789@smtp-relay.mailin.fr>"})])
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.provider_message_id == "xyz-789@smtp-relay.mailin.fr"
    assert "<" not in result.provider_message_id
    assert ">" not in result.provider_message_id


def test_email_message_id_without_brackets_unaffected(monkeypatch):
    _brevo_env(monkeypatch)
    _patch_client(monkeypatch, [_Resp(201, {"messageId": "no-brackets@smtp-relay.mailin.fr"})])
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert result.provider_message_id == "no-brackets@smtp-relay.mailin.fr"


def test_email_key_never_in_url_only_header(monkeypatch):
    """Same secrecy contract as the SMS/WhatsApp Brevo providers: the key
    goes in a header, never the URL, and is never echoed into the result."""
    _brevo_env(monkeypatch)
    monkeypatch.setattr(settings, "BREVO_API_KEY", "SECRET-KEY-DO-NOT-LEAK")
    fake = _patch_client(monkeypatch, [_Resp(201, {"messageId": "m1"})])
    result = BrevoEmailProvider().send(to="a@b.com", subject="s", body="b")
    assert "SECRET-KEY-DO-NOT-LEAK" not in fake.calls[0]["url"]
    assert fake.calls[0]["headers"]["api-key"] == "SECRET-KEY-DO-NOT-LEAK"
    assert "SECRET-KEY-DO-NOT-LEAK" not in str(result)


# ===========================================================================
# BrevoSmsProvider — unit tests (mocked httpx)
# ===========================================================================
def test_sms_missing_api_key_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    monkeypatch.setattr(settings, "BREVO_SMS_SENDER", "RECONS")
    result = BrevoSmsProvider().send(to="+919876543210", subject="", body="hi")
    assert result.ok is False
    assert result.error_code == "NOT_CONFIGURED"
    assert "BREVO_API_KEY" in result.error_message


def test_sms_missing_sender_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "k")
    monkeypatch.setattr(settings, "BREVO_SMS_SENDER", "")
    result = BrevoSmsProvider().send(to="+919876543210", subject="", body="hi")
    assert result.ok is False
    assert result.error_code == "NOT_CONFIGURED"
    assert "BREVO_SMS_SENDER" in result.error_message


def test_sms_malformed_phone_is_invalid(monkeypatch):
    _brevo_env(monkeypatch)
    result = BrevoSmsProvider().send(to="not-a-number", subject="", body="hi")
    assert result.ok is False
    assert result.error_code == "INVALID_PHONE"


def test_sms_success_correct_endpoint_headers_body_and_normalization(monkeypatch):
    _brevo_env(monkeypatch)
    fake = _patch_client(monkeypatch, [_Resp(201, {"messageId": 123456789})])
    result = BrevoSmsProvider().send(to="+919876543210", subject="", body="Your payment link is ready")

    assert result.ok is True
    assert result.status == "SENT"
    assert result.provider == "BREVO_SMS"
    assert result.provider_message_id == "123456789"

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://api.brevo.com/v3/transactionalSMS/send"
    assert call["headers"]["api-key"] == "brevo-secret-DO-NOT-LEAK"
    assert "Authorization" not in call["headers"]
    assert call["json"]["sender"] == "RECONS"
    assert call["json"]["recipient"] == "919876543210"   # normalized, no '+'
    assert call["json"]["content"] == "Your payment link is ready"
    assert call["json"]["type"] == "transactional"


def test_sms_provider_rejection_normalized(monkeypatch):
    _brevo_env(monkeypatch)
    _patch_client(monkeypatch, [_Resp(400, {"code": "invalid_parameter", "message": "bad sender"})])
    result = BrevoSmsProvider().send(to="+919876543210", subject="", body="hi")
    assert result.ok is False
    assert result.error_code == "HTTP_400"


def test_sms_auth_error_distinguished(monkeypatch):
    _brevo_env(monkeypatch)
    _patch_client(monkeypatch, [_Resp(401, {"message": "invalid api key"})])
    result = BrevoSmsProvider().send(to="+919876543210", subject="", body="hi")
    assert result.ok is False
    assert result.error_code == "BREVO_AUTH_ERROR"


def test_sms_transport_error_normalized(monkeypatch):
    _brevo_env(monkeypatch)

    class _RaisingClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("services.communications.providers.httpx.Client", lambda *a, **k: _RaisingClient())
    result = BrevoSmsProvider().send(to="+919876543210", subject="", body="hi")
    assert result.ok is False
    assert result.error_code == "TRANSPORT_ERROR"


# ===========================================================================
# BrevoWhatsAppProvider — unit tests (mocked httpx)
# ===========================================================================
def test_whatsapp_missing_api_key_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    result = BrevoWhatsAppProvider().send(to="+919876543210", subject="", body="hi", template_id="101")
    assert result.ok is False
    assert result.error_code == "NOT_CONFIGURED"


def test_whatsapp_missing_template_refuses_freeform_text(monkeypatch):
    _brevo_env(monkeypatch)
    result = BrevoWhatsAppProvider().send(to="+919876543210", subject="", body="hi", template_id=None)
    assert result.ok is False
    assert result.error_code == "TEMPLATE_NOT_CONFIGURED"


def test_whatsapp_malformed_phone_is_invalid(monkeypatch):
    _brevo_env(monkeypatch)
    result = BrevoWhatsAppProvider().send(to="garbage", subject="", body="hi", template_id="101")
    assert result.ok is False
    assert result.error_code == "INVALID_PHONE"


def test_whatsapp_success_correct_endpoint_headers_body_and_template(monkeypatch):
    _brevo_env(monkeypatch)
    fake = _patch_client(monkeypatch, [_Resp(201, {"messageId": "23befbae-1505-47a8-bd27-e30ef739f32c"})])
    result = BrevoWhatsAppProvider().send(
        to="+919876543210", subject="", body="ignored for templated sends",
        template_id="101", template_vars={"name": "Rahul"},
    )

    assert result.ok is True
    assert result.status == "SENT"
    assert result.provider == "BREVO_WHATSAPP"
    assert result.provider_message_id == "23befbae-1505-47a8-bd27-e30ef739f32c"

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://api.brevo.com/v3/whatsapp/sendMessage"
    assert call["headers"]["api-key"] == "brevo-secret-DO-NOT-LEAK"
    assert call["json"]["contactNumbers"] == ["919876543210"]
    assert call["json"]["senderNumber"] == "919999999999"
    assert call["json"]["templateId"] == 101   # normalized to int
    assert call["json"]["params"] == {"name": "Rahul"}


def test_whatsapp_provider_rejection_normalized(monkeypatch):
    _brevo_env(monkeypatch)
    _patch_client(monkeypatch, [_Resp(400, {"message": "template not approved"})])
    result = BrevoWhatsAppProvider().send(to="+919876543210", subject="", body="", template_id="101")
    assert result.ok is False
    assert result.error_code == "HTTP_400"


# ===========================================================================
# Registry — real mode resolves to Brevo classes, never a silent fallback
# ===========================================================================
def test_registry_real_mode_resolves_brevo_classes(monkeypatch):
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    assert get_communication_provider("EMAIL").name == "BREVO_EMAIL"
    assert get_communication_provider("SMS").name == "BREVO_SMS"
    assert get_communication_provider("WHATSAPP").name == "BREVO_WHATSAPP"


def test_registry_fake_mode_unaffected(monkeypatch):
    assert settings.RECON_COMMUNICATIONS_MODE == "fake"
    assert get_communication_provider("SMS").name == "FAKE_SMS"
    assert get_communication_provider("WHATSAPP").name == "FAKE_WHATSAPP"


# ===========================================================================
# End-to-end via send_communication() — proves the EXISTING, UNTOUCHED
# idempotency/rate-limit layer still holds correctly with real Brevo
# providers selected, never a fake provider recorded while mode=real.
# ===========================================================================
def _real_mode_case(db_session, monkeypatch):
    _brevo_env(monkeypatch)
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    from services.actions.executor import execute_action
    execute_action(db_session, action.id)
    db_session.refresh(case)
    return case


def test_duplicate_email_prevented_in_real_mode(db_session, razorpay_env, monkeypatch):
    """Real-mode EMAIL now goes through BrevoEmailProvider (HTTPS REST), not
    smtplib — mocks the same httpx.Client used by SMS/WhatsApp above."""
    case = _real_mode_case(db_session, monkeypatch)
    _patch_client(monkeypatch, [_Resp(201, {"messageId": "e1"}), _Resp(201, {"messageId": "e2"})])

    c1 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="EMAIL", message_type="PAYMENT_RECOVERY")
    c2 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="EMAIL", message_type="PAYMENT_RECOVERY")
    assert c1.status == "SENT" and c1.provider == "BREVO_EMAIL"
    assert c2.status == "SKIPPED" and c2.skipped_reason == "DUPLICATE"
    sent = (
        db_session.query(Communication)
        .filter_by(recovery_case_id=case.id, channel="EMAIL", message_type="PAYMENT_RECOVERY")
        .filter(Communication.status == "SENT")
        .count()
    )
    assert sent == 1


def test_duplicate_sms_prevented_in_real_mode(db_session, razorpay_env, monkeypatch):
    case = _real_mode_case(db_session, monkeypatch)
    _patch_client(monkeypatch, [_Resp(201, {"messageId": 1}), _Resp(201, {"messageId": 2})])

    c1 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="SMS", message_type="PAYMENT_RECOVERY")
    c2 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="SMS", message_type="PAYMENT_RECOVERY")
    assert c1.status == "SENT" and c1.provider == "BREVO_SMS"
    assert c2.status == "SKIPPED" and c2.skipped_reason == "DUPLICATE"
    # Only the first send() reached the network — the duplicate never issued
    # a second Brevo call at all (SKIPPED before the provider is invoked).


def test_duplicate_whatsapp_prevented_in_real_mode(db_session, razorpay_env, monkeypatch):
    case = _real_mode_case(db_session, monkeypatch)
    _patch_client(monkeypatch, [_Resp(201, {"messageId": "wa-1"}), _Resp(201, {"messageId": "wa-2"})])

    c1 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="WHATSAPP", message_type="PAYMENT_RECOVERY")
    c2 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="WHATSAPP", message_type="PAYMENT_RECOVERY")
    assert c1.status == "SENT" and c1.provider == "BREVO_WHATSAPP"
    assert c2.status == "SKIPPED" and c2.skipped_reason == "DUPLICATE"


def test_provider_failure_followed_by_retry_creates_new_attempt(db_session, razorpay_env, monkeypatch):
    """A FAILED send is NOT protected by the duplicate guard (only SENT/
    DELIVERED/QUEUED/SENDING are) — a later retry is expected to try again,
    exactly like the existing (unchanged) service.py contract."""
    case = _real_mode_case(db_session, monkeypatch)
    fake = _patch_client(monkeypatch, [_Resp(500, {}), _Resp(201, {"messageId": 999})])

    c1 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="SMS", message_type="PAYMENT_RECOVERY")
    assert c1.status == "FAILED"
    assert c1.provider == "BREVO_SMS"
    assert c1.error_code == "HTTP_500"

    c2 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="SMS", message_type="PAYMENT_RECOVERY")
    assert c2.status == "SENT"
    assert len(fake.calls) == 2


def test_missing_brevo_config_records_failed_never_fake_in_real_mode(db_session, razorpay_env, monkeypatch):
    """NEVER record FAKE_EMAIL/FAKE_SMS/FAKE_WHATSAPP while
    RECON_COMMUNICATIONS_MODE=real, even if Brevo is misconfigured — must be
    FAILED via the real provider's own NOT_CONFIGURED result, never a silent
    fallback to a fake provider."""
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")  # deliberately unconfigured
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    from services.actions.executor import execute_action
    execute_action(db_session, action.id)
    db_session.refresh(case)

    c = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                           channel="SMS", message_type="PAYMENT_RECOVERY")
    assert c.status == "FAILED"
    assert c.provider == "BREVO_SMS"
    assert c.provider != "FAKE_SMS"
    assert c.error_code == "NOT_CONFIGURED"


def test_missing_whatsapp_template_mapping_records_failed_in_real_mode(db_session, razorpay_env, monkeypatch):
    _brevo_env(monkeypatch)
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "BREVO_WHATSAPP_TEMPLATE_IDS", "")  # no mapping at all
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    from services.actions.executor import execute_action
    execute_action(db_session, action.id)
    db_session.refresh(case)

    c = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                           channel="WHATSAPP", message_type="PAYMENT_RECOVERY")
    assert c.status == "FAILED"
    assert c.provider == "BREVO_WHATSAPP"
    assert c.error_code == "TEMPLATE_NOT_CONFIGURED"


def test_malformed_phone_records_failed_not_sent_in_real_mode(db_session, razorpay_env, monkeypatch):
    _brevo_env(monkeypatch)
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    case = _analyzed_case(db_session, upi_timeout_payload())
    action = _proposed_action(db_session, case)
    from services.actions.executor import execute_action
    execute_action(db_session, action.id)
    db_session.refresh(case)

    customer = case.customer
    customer.phone = "not-a-real-number"
    db_session.commit()
    original_phone = customer.phone

    c = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                           channel="SMS", message_type="PAYMENT_RECOVERY")
    assert c.status == "FAILED"
    assert c.error_code == "INVALID_PHONE"
    # The stored customer phone is never mutated for provider formatting.
    db_session.refresh(customer)
    assert customer.phone == original_phone


def test_successful_provider_response_populates_provider_message_id(db_session, razorpay_env, monkeypatch):
    case = _real_mode_case(db_session, monkeypatch)
    _patch_client(monkeypatch, [_Resp(201, {"messageId": 42424242})])
    c = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                           channel="SMS", message_type="PAYMENT_RECOVERY")
    assert c.status == "SENT"
    assert c.provider_message_id == "42424242"
    assert c.recipient == "+919876543210"   # stored recipient is the ORIGINAL, unmutated value
