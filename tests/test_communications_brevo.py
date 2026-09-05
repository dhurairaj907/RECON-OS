"""
RECON OS — Phase 7: Brevo Delivery-Webhook Correlation Tests  (SAFETY-CRITICAL)

Covers: the RECON-owned Message-ID now captured on real SMTP sends, the
Brevo-specific payload translator, Brevo's Bearer-token authentication
(additive, never replacing the existing HMAC path), the shared
SENT->DELIVERED/FAILED state machine reused by both webhook routes, and
non-terminal Brevo events (softBounce/deferred/spam) that must never
fabricate a status change. No real email is sent by these tests — the SMTP
transport itself is faked exactly like the existing Phase 7 SMTP tests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest

from config import settings
from models.communication import Communication
from services.communications.brevo_webhook import translate_brevo_event
from services.communications.providers import SmtpEmailProvider
from services.communications.webhook_verifier import verify_brevo_webhook_token
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


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=10):
        self.sent = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, pw):
        pass

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent.append((from_addr, to_addrs, msg))


@pytest.fixture
def smtp_env(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp-relay.brevo.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(settings, "SMTP_USE_SSL", False)
    _FakeSMTP.instances = []
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)
    yield


class _FakeBrevoEmailResp:
    status_code = 201

    def json(self):
        return {"messageId": f"<{uuid.uuid4().hex}@smtp-relay.brevo.com>"}


class _FakeBrevoHttpxClient:
    """Fakes services.communications.providers.httpx.Client for
    BrevoEmailProvider — real-mode EMAIL now goes through Brevo's HTTPS REST
    API (POST /v3/smtp/email), not smtplib. Never a real network call."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, *a, **k):
        return _FakeBrevoEmailResp()


def _brevo_real_email_env(monkeypatch, *, from_email="sender@example.com"):
    """Selects the real Brevo REST email provider with a faked HTTP
    transport — the real-mode-email counterpart to the smtp_env fixture
    above, which still exercises SmtpEmailProvider directly and is
    unaffected by this."""
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "test-brevo-key")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", from_email)
    monkeypatch.setattr("services.communications.providers.httpx.Client",
                        lambda *a, **k: _FakeBrevoHttpxClient())


# ===========================================================================
# Message-ID generation — real, deterministic-per-send, never fabricated
# ===========================================================================
def test_smtp_provider_generates_and_returns_message_id(smtp_env):
    result = SmtpEmailProvider().send(to="dhuraisingham907@gmail.com", subject="Test", body="Body")
    assert result.ok is True
    assert result.provider_message_id  # populated now, unlike before this phase
    assert "@" in result.provider_message_id
    assert not result.provider_message_id.startswith("<")  # canonicalized, bracket-free


def test_smtp_provider_message_id_matches_actual_sent_header(smtp_env):
    """No fabrication: the returned provider_message_id must be the exact
    Message-ID header actually placed on the wire, not an unrelated value."""
    result = SmtpEmailProvider().send(to="dhuraisingham907@gmail.com", subject="Test", body="Body")
    sent_raw_message = _FakeSMTP.instances[-1].sent[0][2]
    assert f"Message-ID: <{result.provider_message_id}>" in sent_raw_message


def test_smtp_provider_message_id_uses_from_domain_not_hostname(smtp_env):
    result = SmtpEmailProvider().send(to="x@example.com", subject="s", body="b")
    assert result.provider_message_id.endswith("@example.com")


def test_provider_message_id_persisted_via_send_communication(db_session, razorpay_env, monkeypatch):
    """Real-mode EMAIL now resolves to BrevoEmailProvider (HTTPS REST) — see
    services/communications/providers.py's _REAL registry."""
    _brevo_real_email_env(monkeypatch)
    case = _analyzed_case(db_session, upi_timeout_payload())
    comm = send_communication(db_session, merchant_id=case.merchant_id, case=case,
                              channel="EMAIL", message_type="PAYMENT_FAILED")
    assert comm.status == "SENT"
    assert comm.provider_message_id
    assert comm.provider == "BREVO_EMAIL"


# ===========================================================================
# Brevo payload translator — pure function
# ===========================================================================
def test_translate_delivered_event():
    t = translate_brevo_event({
        "event": "delivered", "message-id": "<abc123@example.com>", "id": 999, "ts_event": 1700000000,
    })
    assert t["status"] == "delivered"
    assert t["provider_message_id"] == "abc123@example.com"   # brackets stripped
    assert t["event_id"] == "brevo:999:1700000000"
    assert t["error_reason"] is None


def test_translate_hard_bounce_is_terminal_failure():
    t = translate_brevo_event({"event": "hardBounce", "message-id": "abc@example.com", "id": 1, "ts_event": 1})
    assert t["status"] == "failed"
    assert t["error_reason"] == "hardBounce"


def test_translate_blocked_and_invalid_are_terminal_failure():
    for ev in ("blocked", "invalid"):
        t = translate_brevo_event({"event": ev, "message-id": "abc@example.com", "id": 1, "ts_event": 1})
        assert t["status"] == "failed"


@pytest.mark.parametrize("ev", ["softBounce", "deferred", "spam", "someFutureEvent"])
def test_translate_non_terminal_events_never_fabricate_status(ev):
    """softBounce/deferred are transient (Brevo may still deliver later);
    spam means the message WAS delivered — none of these may be reported as
    a status transition RECON's state machine can't justify."""
    t = translate_brevo_event({"event": ev, "message-id": "abc@example.com", "id": 1, "ts_event": 1})
    assert t["status"] is None


def test_translate_strips_angle_brackets_both_forms():
    with_brackets = translate_brevo_event({"event": "delivered", "message-id": "<x@y.com>", "id": 1, "ts_event": 1})
    without_brackets = translate_brevo_event({"event": "delivered", "message-id": "x@y.com", "id": 1, "ts_event": 1})
    assert with_brackets["provider_message_id"] == without_brackets["provider_message_id"] == "x@y.com"


def test_translate_missing_message_id_returns_none_not_fabricated():
    t = translate_brevo_event({"event": "delivered", "id": 1, "ts_event": 1})
    assert t["provider_message_id"] is None


# ===========================================================================
# Brevo authentication — additive Bearer token, fail-closed, never HMAC
# ===========================================================================
def test_brevo_token_verification_valid(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "brevo_secret_123")
    assert verify_brevo_webhook_token("Bearer brevo_secret_123") is True


def test_brevo_token_verification_invalid(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "brevo_secret_123")
    assert verify_brevo_webhook_token("Bearer wrong_token") is False


def test_brevo_token_verification_missing_header(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "brevo_secret_123")
    assert verify_brevo_webhook_token(None) is False


def test_brevo_token_verification_fails_closed_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "")
    assert verify_brevo_webhook_token("Bearer anything") is False


def test_brevo_token_never_falls_back_to_unsigned_allowance(monkeypatch):
    """COMMUNICATION_ALLOW_UNSIGNED_WEBHOOKS must have zero effect on the
    Brevo path — there is no unsigned opt-out for it."""
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "")
    monkeypatch.setattr(settings, "COMMUNICATION_ALLOW_UNSIGNED_WEBHOOKS", True)
    assert verify_brevo_webhook_token(None) is False
    assert verify_brevo_webhook_token("Bearer whatever") is False


# ===========================================================================
# Brevo webhook endpoint — end-to-end via the real HTTP route
# ===========================================================================
def _send_real_email(client, monkeypatch, smtp_env_active=True):
    """Sends one message via the real send endpoint with the real Brevo REST
    email provider selected (mode='real'), but the actual network transport
    is ALWAYS faked here — this must never attempt a real connection to
    Brevo, and must never send a real email to any test-fixture address."""
    _brevo_real_email_env(monkeypatch)
    cn = _api_analyzed_case(client)
    res = client.post(f"/api/v1/recovery-cases/{cn}/communications/send", json={
        "channel": "EMAIL", "message_type": "PAYMENT_FAILED",
    })
    assert res.status_code == 200, res.text
    return res.json()["communication"]


def test_brevo_webhook_missing_auth_rejected(client):
    body = json.dumps({"event": "delivered", "message-id": "x@y.com", "id": 1, "ts_event": 1}).encode()
    res = client.post("/api/v1/webhooks/communications/brevo", content=body,
                      headers={"Content-Type": "application/json"})
    assert res.status_code == 401


def test_brevo_webhook_invalid_auth_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    body = json.dumps({"event": "delivered", "message-id": "x@y.com", "id": 1, "ts_event": 1}).encode()
    res = client.post("/api/v1/webhooks/communications/brevo", content=body,
                      headers={"Content-Type": "application/json", "Authorization": "Bearer wrong_token"})
    assert res.status_code == 401


def test_brevo_webhook_malformed_json_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    res = client.post("/api/v1/webhooks/communications/brevo", content=b"not json",
                      headers={"Content-Type": "application/json", "Authorization": "Bearer correct_token"})
    assert res.status_code == 400


def test_brevo_webhook_missing_message_id_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    body = json.dumps({"event": "delivered", "id": 1, "ts_event": 1}).encode()
    res = client.post("/api/v1/webhooks/communications/brevo", content=body,
                      headers={"Content-Type": "application/json", "Authorization": "Bearer correct_token"})
    assert res.status_code == 400


def test_brevo_webhook_unknown_message_id_ignored(client, monkeypatch):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    body = json.dumps({"event": "delivered", "message-id": "no-such-id@example.com", "id": 1, "ts_event": 1}).encode()
    res = client.post("/api/v1/webhooks/communications/brevo", content=body,
                      headers={"Content-Type": "application/json", "Authorization": "Bearer correct_token"})
    assert res.status_code == 200
    assert res.json()["reason"] == "unknown_provider_message_id"


def test_brevo_webhook_delivered_transitions_sent_to_delivered(client, monkeypatch, razorpay_env):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    comm = _send_real_email(client, monkeypatch)
    assert comm["status"] == "SENT"
    msg_id = comm["provider_message_id"]
    assert msg_id

    body = json.dumps({"event": "delivered", "message-id": msg_id, "id": 42, "ts_event": 1700000001}).encode()
    res = client.post("/api/v1/webhooks/communications/brevo", content=body,
                      headers={"Content-Type": "application/json", "Authorization": "Bearer correct_token"})
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "communication_id": comm["id"], "new_status": "DELIVERED"}


def test_brevo_webhook_duplicate_event_is_idempotent(client, monkeypatch, razorpay_env):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    comm = _send_real_email(client, monkeypatch)
    msg_id = comm["provider_message_id"]
    body = json.dumps({"event": "delivered", "message-id": msg_id, "id": 42, "ts_event": 1700000001}).encode()
    headers = {"Content-Type": "application/json", "Authorization": "Bearer correct_token"}

    first = client.post("/api/v1/webhooks/communications/brevo", content=body, headers=headers)
    assert first.json()["new_status"] == "DELIVERED"
    second = client.post("/api/v1/webhooks/communications/brevo", content=body, headers=headers)
    assert second.json() == {"status": "ignored", "reason": "duplicate_event", "communication_id": comm["id"]}


def test_brevo_webhook_hard_bounce_transitions_to_failed(client, monkeypatch, razorpay_env):
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    comm = _send_real_email(client, monkeypatch)
    msg_id = comm["provider_message_id"]

    body = json.dumps({"event": "hardBounce", "message-id": msg_id, "id": 5, "ts_event": 2}).encode()
    res = client.post("/api/v1/webhooks/communications/brevo", content=body,
                      headers={"Content-Type": "application/json", "Authorization": "Bearer correct_token"})
    assert res.json()["new_status"] == "FAILED"


def test_brevo_webhook_soft_bounce_does_not_change_status(client, monkeypatch, razorpay_env):
    """A transient event must never flip SENT to a terminal state."""
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    comm = _send_real_email(client, monkeypatch)
    msg_id = comm["provider_message_id"]

    body = json.dumps({"event": "softBounce", "message-id": msg_id, "id": 6, "ts_event": 3}).encode()
    res = client.post("/api/v1/webhooks/communications/brevo", content=body,
                      headers={"Content-Type": "application/json", "Authorization": "Bearer correct_token"})
    assert res.status_code == 200
    assert res.json()["status"] == "acknowledged"

    history = client.get(f"/api/v1/recovery-cases/{comm['recovery_case_id']}/communications").json()
    # status unaffected — still SENT
    row = next(i for i in history["items"] if i["id"] == comm["id"])
    assert row["status"] == "SENT"


def test_brevo_webhook_spam_does_not_mark_failed(client, monkeypatch, razorpay_env):
    """spam means it WAS delivered — must never be recorded as FAILED."""
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    comm = _send_real_email(client, monkeypatch)
    msg_id = comm["provider_message_id"]

    body = json.dumps({"event": "spam", "message-id": msg_id, "id": 7, "ts_event": 4}).encode()
    res = client.post("/api/v1/webhooks/communications/brevo", content=body,
                      headers={"Content-Type": "application/json", "Authorization": "Bearer correct_token"})
    assert res.json()["status"] == "acknowledged"

    detail = client.get(f"/api/v1/recovery-cases/{comm['recovery_case_id']}/communications").json()
    row = next(i for i in detail["items"] if i["id"] == comm["id"])
    assert row["status"] != "FAILED"


def test_brevo_webhook_terminal_state_protection(client, monkeypatch, razorpay_env):
    """Once DELIVERED, a later hardBounce for the same message-id must never
    move it backwards to FAILED."""
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    comm = _send_real_email(client, monkeypatch)
    msg_id = comm["provider_message_id"]
    headers = {"Content-Type": "application/json", "Authorization": "Bearer correct_token"}

    delivered_body = json.dumps({"event": "delivered", "message-id": msg_id, "id": 1, "ts_event": 1}).encode()
    client.post("/api/v1/webhooks/communications/brevo", content=delivered_body, headers=headers)

    bounce_body = json.dumps({"event": "hardBounce", "message-id": msg_id, "id": 2, "ts_event": 2}).encode()
    res = client.post("/api/v1/webhooks/communications/brevo", content=bounce_body, headers=headers)
    assert res.json()["reason"] == "communication already DELIVERED"

    detail = client.get(f"/api/v1/recovery-cases/{comm['recovery_case_id']}/communications").json()
    row = next(i for i in detail["items"] if i["id"] == comm["id"])
    assert row["status"] == "DELIVERED"


def test_brevo_webhook_organization_isolation(unauthenticated_client, monkeypatch):
    """A Brevo event for Org A's message-id must never be locatable/affect
    anything belonging to another organization — the lookup is purely by the
    globally-unique provider_message_id, never an org id from the payload
    (there isn't one), and each org's Communication rows are still separately
    scoped by merchant_id underneath."""
    monkeypatch.setattr(settings, "BREVO_WEBHOOK_TOKEN", "correct_token")
    _brevo_real_email_env(monkeypatch)
    c = unauthenticated_client
    c.post("/api/v1/auth/register", json={
        "email": "brevo-org-a@recon.test", "password": "Password123!", "organization_name": "Brevo Org A",
    })
    cn_a = _api_analyzed_case(c)
    send_a = c.post(f"/api/v1/recovery-cases/{cn_a}/communications/send", json={
        "channel": "EMAIL", "message_type": "PAYMENT_FAILED",
    }).json()["communication"]

    c.cookies.clear()
    c.post("/api/v1/auth/register", json={
        "email": "brevo-org-b@recon.test", "password": "Password123!", "organization_name": "Brevo Org B",
    })
    cn_b = _api_analyzed_case(c)
    send_b = c.post(f"/api/v1/recovery-cases/{cn_b}/communications/send", json={
        "channel": "EMAIL", "message_type": "PAYMENT_FAILED",
    }).json()["communication"]

    assert send_a["provider_message_id"] != send_b["provider_message_id"]

    body = json.dumps({
        "event": "delivered", "message-id": send_a["provider_message_id"], "id": 1, "ts_event": 1,
    }).encode()
    res = c.post("/api/v1/webhooks/communications/brevo", content=body,
                 headers={"Content-Type": "application/json", "Authorization": "Bearer correct_token"})
    assert res.json()["communication_id"] == send_a["id"]

    # Org B, still logged in as org B, sees its own message untouched.
    hist_b = c.get(f"/api/v1/recovery-cases/{cn_b}/communications").json()
    row_b = next(i for i in hist_b["items"] if i["id"] == send_b["id"])
    assert row_b["status"] == "SENT"


# ===========================================================================
# Existing generic HMAC webhook — regression, must be completely unaffected
# ===========================================================================
def _sign(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_existing_generic_hmac_webhook_still_works_after_refactor(client, monkeypatch, razorpay_env):
    monkeypatch.setattr(settings, "COMMUNICATION_WEBHOOK_SECRET", "whsec_generic")
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "fake")
    cn = _api_analyzed_case(client)
    action = _api_propose(client, cn)
    _api_execute(client, action["id"])
    send_res = client.post(f"/api/v1/recovery-cases/{cn}/communications/send", json={
        "channel": "EMAIL", "message_type": "PAYMENT_LINK_CREATED",
    }).json()["communication"]
    assert send_res["status"] == "SENT"

    body = json.dumps({
        "provider_message_id": send_res["provider_message_id"], "event_id": "evt_1", "status": "delivered",
    }).encode()
    res = client.post("/api/v1/webhooks/communications/delivery", content=body,
                      headers={"Content-Type": "application/json", "X-RECON-Comm-Signature": _sign("whsec_generic", body)})
    assert res.status_code == 200
    assert res.json()["new_status"] == "DELIVERED"


def test_generic_hmac_route_rejects_bearer_token_style_auth(client, monkeypatch):
    """The two routes' authentication must never be interchangeable."""
    monkeypatch.setattr(settings, "COMMUNICATION_WEBHOOK_SECRET", "whsec_generic")
    body = json.dumps({"provider_message_id": "x", "event_id": "e1", "status": "delivered"}).encode()
    res = client.post("/api/v1/webhooks/communications/delivery", content=body,
                      headers={"Content-Type": "application/json", "Authorization": "Bearer whsec_generic"})
    assert res.status_code == 401
