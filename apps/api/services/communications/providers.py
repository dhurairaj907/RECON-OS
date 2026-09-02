"""
RECON OS — Phase 5: Communication Provider Adapters

Same shape as integrations/razorpay/adapter.py: a small, bounded interface
that never raises, always returns a structured result, and never claims a
delivery the provider didn't actually confirm. AI/strategy code never touches
these directly — only services/communications/service.py, itself only
reachable through the policy-gated decision in this same package.

Fake providers (the default — RECON_COMMUNICATIONS_MODE=fake) are
deterministic and clearly self-identify as TEST/DEMO; they report SENT, never
DELIVERED (delivery is a real-world confirmation a fake provider cannot
honestly make).

Real providers use only what's already a dependency (stdlib smtplib for
email; httpx — already required — for a generic provider webhook for SMS/
WhatsApp, since no vendor SDK is available/authorized in this phase). Missing
credentials produce a structured NOT_CONFIGURED result, exactly like the
Razorpay adapter — they never raise and never fall back to the fake provider.
"""

from __future__ import annotations

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.utils import make_msgid
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger("recon.services.communications.providers")


@dataclass
class ProviderResult:
    ok: bool
    status: str = "FAILED"                 # SENT | FAILED (providers never claim DELIVERED)
    provider: str = ""
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class CommunicationProvider:
    name = "BASE"

    def send(
        self, *, to: str, subject: str, body: str,
        template_id: Optional[str] = None, template_vars: Optional[dict] = None,
    ) -> ProviderResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Fake providers — deterministic, dev/test default, never claim real delivery
# ---------------------------------------------------------------------------
class FakeEmailProvider(CommunicationProvider):
    name = "FAKE_EMAIL"

    def send(self, *, to: str, subject: str, body: str,
              template_id: Optional[str] = None, template_vars: Optional[dict] = None) -> ProviderResult:
        msg_id = f"fake-email-{uuid.uuid4().hex[:12]}"
        logger.info("[TEST/DEMO] FAKE EMAIL to %s — subject=%r id=%s", to, subject, msg_id)
        return ProviderResult(ok=True, status="SENT", provider=self.name, provider_message_id=msg_id)


class FakeSMSProvider(CommunicationProvider):
    name = "FAKE_SMS"

    def send(self, *, to: str, subject: str, body: str,
              template_id: Optional[str] = None, template_vars: Optional[dict] = None) -> ProviderResult:
        msg_id = f"fake-sms-{uuid.uuid4().hex[:12]}"
        logger.info("[TEST/DEMO] FAKE SMS to %s — id=%s", to, msg_id)
        return ProviderResult(ok=True, status="SENT", provider=self.name, provider_message_id=msg_id)


class FakeWhatsAppProvider(CommunicationProvider):
    name = "FAKE_WHATSAPP"

    def send(self, *, to: str, subject: str, body: str,
              template_id: Optional[str] = None, template_vars: Optional[dict] = None) -> ProviderResult:
        msg_id = f"fake-whatsapp-{uuid.uuid4().hex[:12]}"
        logger.info("[TEST/DEMO] FAKE WHATSAPP to %s — id=%s (template=%s)", to, msg_id, template_id)
        return ProviderResult(ok=True, status="SENT", provider=self.name, provider_message_id=msg_id)


def _strip_angle_brackets(value: str) -> str:
    """RFC 5322 Message-ID header values look like '<id@domain>'; this
    canonicalizes to the bare 'id@domain' form so it compares equal
    regardless of which form a webhook later reports it in — see
    services/communications/brevo_webhook.py's matching canonicalization."""
    v = (value or "").strip()
    if v.startswith("<") and v.endswith(">"):
        v = v[1:-1]
    return v


# ---------------------------------------------------------------------------
# Real providers — env-configured only, never invented, never committed
# ---------------------------------------------------------------------------
class SmtpEmailProvider(CommunicationProvider):
    name = "SMTP_EMAIL"

    def send(self, *, to: str, subject: str, body: str,
              template_id: Optional[str] = None, template_vars: Optional[dict] = None) -> ProviderResult:
        if not (settings.SMTP_HOST and settings.SMTP_FROM_EMAIL):
            return ProviderResult(ok=False, provider=self.name, error_code="NOT_CONFIGURED",
                                  error_message="SMTP_HOST / SMTP_FROM_EMAIL are not set.")
        if not to:
            return ProviderResult(ok=False, provider=self.name, error_code="NO_RECIPIENT",
                                  error_message="No recipient email address provided.")
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to
        # RECON-owned, RFC 5322 Message-ID — generated with stdlib
        # email.utils.make_msgid() (no new dependency), scoped to the
        # sending domain rather than this machine's hostname. This is the
        # ONLY correlation identifier RECON's SMTP path can obtain at send
        # time (smtplib.sendmail() itself returns none); whether the
        # configured relay (e.g. Brevo) echoes this exact value back in its
        # delivery webhook is verified separately, never assumed here — see
        # services/communications/brevo_webhook.py.
        from_domain = settings.SMTP_FROM_EMAIL.rsplit("@", 1)[-1] if "@" in settings.SMTP_FROM_EMAIL else None
        message_id = _strip_angle_brackets(make_msgid(domain=from_domain))
        msg["Message-ID"] = f"<{message_id}>"
        try:
            if settings.SMTP_USE_SSL:
                server_cm = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            else:
                server_cm = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            with server_cm as server:
                if not settings.SMTP_USE_SSL:
                    server.starttls()
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM_EMAIL, [to], msg.as_string())
            return ProviderResult(ok=True, status="SENT", provider=self.name, provider_message_id=message_id)
        except smtplib.SMTPAuthenticationError:
            logger.warning("SMTP authentication failed for %s", settings.SMTP_USERNAME)
            return ProviderResult(ok=False, provider=self.name, error_code="SMTP_AUTH_ERROR",
                                  error_message="SMTP authentication was rejected.")
        except (OSError, smtplib.SMTPException) as e:
            logger.warning("SMTP send failed: %s", type(e).__name__)
            return ProviderResult(ok=False, provider=self.name, error_code="SMTP_ERROR",
                                  error_message="SMTP transport error.")


def _extract_provider_message_id(payload: dict) -> Optional[str]:
    """Best-effort extraction across the field names common generic SMS/WhatsApp
    HTTP APIs use — never invents one when the provider didn't return any."""
    if not isinstance(payload, dict):
        return None
    for key in ("id", "message_id", "messageId", "sid", "message_sid"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


class WebhookSMSProvider(CommunicationProvider):
    """Generic HTTP webhook adapter — no vendor SDK dependency. Posts
    {to, body, api_key} to SMS_PROVIDER_WEBHOOK_URL; 2xx is treated as sent."""
    name = "WEBHOOK_SMS"

    def send(self, *, to: str, subject: str, body: str,
              template_id: Optional[str] = None, template_vars: Optional[dict] = None) -> ProviderResult:
        if not settings.SMS_PROVIDER_WEBHOOK_URL:
            return ProviderResult(ok=False, provider=self.name, error_code="NOT_CONFIGURED",
                                  error_message="SMS_PROVIDER_WEBHOOK_URL is not set.")
        if not to:
            return ProviderResult(ok=False, provider=self.name, error_code="NO_RECIPIENT",
                                  error_message="No recipient phone number provided.")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(settings.SMS_PROVIDER_WEBHOOK_URL,
                                   json={"to": to, "body": body},
                                   headers={"Authorization": f"Bearer {settings.SMS_PROVIDER_API_KEY}"}
                                   if settings.SMS_PROVIDER_API_KEY else {})
        except httpx.HTTPError:
            return ProviderResult(ok=False, provider=self.name, error_code="TRANSPORT_ERROR",
                                  error_message="SMS provider webhook unreachable.")
        if resp.status_code >= 400:
            return ProviderResult(ok=False, provider=self.name, error_code=f"HTTP_{resp.status_code}",
                                  error_message="SMS provider webhook rejected the request.")
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        return ProviderResult(ok=True, status="SENT", provider=self.name,
                              provider_message_id=_extract_provider_message_id(payload))


class WebhookWhatsAppProvider(CommunicationProvider):
    """Generic HTTP webhook adapter for a WhatsApp Business API-style
    provider. When WHATSAPP_REQUIRE_TEMPLATE is set (the default — matches
    how real WhatsApp Business APIs behave outside an open customer session),
    a resolved template_id is mandatory: arbitrary free text is never
    substituted for an approved template."""
    name = "WEBHOOK_WHATSAPP"

    def send(self, *, to: str, subject: str, body: str,
              template_id: Optional[str] = None, template_vars: Optional[dict] = None) -> ProviderResult:
        if not settings.WHATSAPP_PROVIDER_WEBHOOK_URL:
            return ProviderResult(ok=False, provider=self.name, error_code="NOT_CONFIGURED",
                                  error_message="WHATSAPP_PROVIDER_WEBHOOK_URL is not set.")
        if not to:
            return ProviderResult(ok=False, provider=self.name, error_code="NO_RECIPIENT",
                                  error_message="No recipient phone number provided.")
        if settings.WHATSAPP_REQUIRE_TEMPLATE and not template_id:
            return ProviderResult(ok=False, provider=self.name, error_code="TEMPLATE_NOT_CONFIGURED",
                                  error_message="No approved WhatsApp template is configured for this "
                                                "message type (WHATSAPP_TEMPLATE_IDS) — refusing to send "
                                                "unapproved free text as a template message.")
        payload = {"to": to}
        if template_id:
            payload["template_id"] = template_id
            payload["template_vars"] = template_vars or {}
        else:
            payload["body"] = body
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(settings.WHATSAPP_PROVIDER_WEBHOOK_URL, json=payload,
                                   headers={"Authorization": f"Bearer {settings.WHATSAPP_PROVIDER_API_KEY}"}
                                   if settings.WHATSAPP_PROVIDER_API_KEY else {})
        except httpx.HTTPError:
            return ProviderResult(ok=False, provider=self.name, error_code="TRANSPORT_ERROR",
                                  error_message="WhatsApp provider webhook unreachable.")
        if resp.status_code >= 400:
            return ProviderResult(ok=False, provider=self.name, error_code=f"HTTP_{resp.status_code}",
                                  error_message="WhatsApp provider webhook rejected the request.")
        try:
            resp_payload = resp.json()
        except ValueError:
            resp_payload = {}
        return ProviderResult(ok=True, status="SENT", provider=self.name,
                              provider_message_id=_extract_provider_message_id(resp_payload))


_FAKE = {"EMAIL": FakeEmailProvider, "SMS": FakeSMSProvider, "WHATSAPP": FakeWhatsAppProvider}
_REAL = {"EMAIL": SmtpEmailProvider, "SMS": WebhookSMSProvider, "WHATSAPP": WebhookWhatsAppProvider}


def get_communication_provider(channel: str) -> CommunicationProvider:
    registry = _FAKE if settings.RECON_COMMUNICATIONS_MODE != "real" else _REAL
    cls = registry.get(channel.upper())
    if cls is None:
        raise ValueError(f"Unknown communication channel: {channel}")
    return cls()
