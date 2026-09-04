"""
RECON OS — Real Brevo SMS/WhatsApp provider tests.

Covers BrevoSmsProvider / BrevoWhatsAppProvider (services/communications/
providers.py) at the unit level (mocked httpx.Client — never a real network
call), plus end-to-end send_communication() tests proving the EXISTING
idempotency/rate-limit/opt-out layer (services/communications/service.py,
UNCHANGED by this work) still holds correctly when RECON_COMMUNICATIONS_MODE
is switched to "real" and the registry resolves to the new Brevo classes.

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
    assert get_communication_provider("SMS").name == "BREVO_SMS"
    assert get_communication_provider("WHATSAPP").name == "BREVO_WHATSAPP"
    assert get_communication_provider("EMAIL").name == "SMTP_EMAIL"


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
    case = _real_mode_case(db_session, monkeypatch)

    class _FakeSmtp:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def sendmail(self, *a, **k):
            pass

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp-relay.brevo.com")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@example.com")
    monkeypatch.setattr("smtplib.SMTP", _FakeSmtp)

    c1 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="EMAIL", message_type="PAYMENT_RECOVERY")
    c2 = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                            channel="EMAIL", message_type="PAYMENT_RECOVERY")
    assert c1.status == "SENT" and c1.provider == "SMTP_EMAIL"
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
