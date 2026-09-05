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
from typing import Any, Dict, Optional

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


class BrevoEmailProvider(CommunicationProvider):
    """
    Real Brevo transactional email via REST — POST
    https://api.brevo.com/v3/smtp/email, `api-key` header — see
    developers.brevo.com/reference/sendtransacemail. Added because Render's
    Free plan has no Shell access, so outbound SMTP from the deployed
    container cannot be reliably exercised/diagnosed; HTTPS REST works
    identically to the SMS/WhatsApp Brevo providers already in this file
    and needs no SMTP port to be reachable.

    SmtpEmailProvider above is left completely intact for local dev/
    backward compatibility — this is an ADDITIONAL provider, not a
    replacement of that class; only the _REAL registry's EMAIL entry
    changes to use this one.

    Reuses the existing SMTP_FROM_EMAIL setting as the sender address so
    existing configuration stays compatible — no new "from" setting is
    introduced (BREVO_SMS_SENDER/BREVO_WHATSAPP_SENDER are channel-specific
    to their own APIs; email's sender identity is already SMTP_FROM_EMAIL).
    """
    name = "BREVO_EMAIL"
    _API_URL = "https://api.brevo.com/v3/smtp/email"

    def send(self, *, to: str, subject: str, body: str,
              template_id: Optional[str] = None, template_vars: Optional[dict] = None) -> ProviderResult:
        if not settings.BREVO_API_KEY:
            return ProviderResult(ok=False, provider=self.name, error_code="NOT_CONFIGURED",
                                  error_message="BREVO_API_KEY is not set.")
        if not settings.SMTP_FROM_EMAIL:
            return ProviderResult(ok=False, provider=self.name, error_code="NOT_CONFIGURED",
                                  error_message="SMTP_FROM_EMAIL is not set.")
        if not to:
            return ProviderResult(ok=False, provider=self.name, error_code="NO_RECIPIENT",
                                  error_message="No recipient email address provided.")

        payload: Dict[str, Any] = {
            "sender": {"email": settings.SMTP_FROM_EMAIL},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        }
        headers = {"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(self._API_URL, json=payload, headers=headers)
        except httpx.TimeoutException:
            logger.warning("Brevo email API request timed out")
            return ProviderResult(ok=False, provider=self.name, error_code="TRANSPORT_ERROR",
                                  error_message="Brevo email API request timed out.")
        except httpx.HTTPError:
            logger.warning("Brevo email API transport error")
            return ProviderResult(ok=False, provider=self.name, error_code="TRANSPORT_ERROR",
                                  error_message="Brevo email API unreachable.")

        if resp.status_code in (401, 403):
            # Never log the response body — it can echo request/key context.
            logger.warning("Brevo email API rejected the request: HTTP %s", resp.status_code)
            return ProviderResult(ok=False, provider=self.name, error_code="BREVO_AUTH_ERROR",
                                  error_message="Brevo rejected the API key.")
        if resp.status_code >= 400:
            logger.warning("Brevo email API error: HTTP %s", resp.status_code)
            return ProviderResult(ok=False, provider=self.name, error_code=f"HTTP_{resp.status_code}",
                                  error_message="Brevo email API rejected the request.")
        try:
            resp_payload = resp.json()
        except ValueError:
            resp_payload = {}
        # Brevo's REST response wraps messageId in RFC 5322 angle brackets
        # (e.g. "<abc@smtp-relay.mailin.fr>"), same as SmtpEmailProvider's
        # own Message-ID above — canonicalize identically (strip brackets)
        # so the stored provider_message_id matches what
        # brevo_webhook.py::_canonical_message_id() looks up from a later
        # delivery-status webhook, which strips brackets on the inbound side
        # regardless of which form the sender used.
        raw_message_id = _extract_provider_message_id(resp_payload)
        # A successful submission means Brevo ACCEPTED the request — never
        # DELIVERED, which only a real delivery confirmation can claim (see
        # services/communications/brevo_webhook.py, unchanged by this work).
        return ProviderResult(ok=True, status="SENT", provider=self.name,
                              provider_message_id=_strip_angle_brackets(raw_message_id) if raw_message_id else None)


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


def _normalize_phone_for_brevo(phone: Optional[str]) -> Optional[str]:
    """
    Converts RECON's stored E.164-style phone (e.g. +919876543210) into
    Brevo's required countrycode+digits form (919876543210) — Brevo's
    SMS/WhatsApp APIs expect digits only, no leading '+' and no separators
    (developers.brevo.com/docs/whatsapp-messages). Read-only: this NEVER
    writes back to Customer.phone — the stored value is never mutated for
    provider formatting, only a local copy is used for the outbound request.
    Returns None (never a guess) if nothing digit-like remains, e.g. for a
    malformed/empty input.
    """
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits or None


# ---------------------------------------------------------------------------
# Brevo — real providers for SMS + WhatsApp (REST API, not the generic
# webhook shape above). Email intentionally has NO Brevo-specific class:
# SmtpEmailProvider already works unmodified against Brevo's SMTP relay.
# ---------------------------------------------------------------------------
class BrevoSmsProvider(CommunicationProvider):
    """
    Real Brevo transactional SMS — POST https://api.brevo.com/v3/transactionalSMS/send,
    authenticated via the `api-key` header (NOT the generic
    `Authorization: Bearer` shape WebhookSMSProvider uses) — see
    developers.brevo.com/docs/transactional-sms-endpoints. Returns a
    structured NOT_CONFIGURED result (never raises, never falls back to
    WebhookSMSProvider or a fake provider) when BREVO_API_KEY or
    BREVO_SMS_SENDER is unset.

    India-specific safety note: BREVO_SMS_SENDER must be a TRAI DLT-
    registered Header for delivery to Indian numbers to actually succeed —
    an unregistered sender is silently dropped by the carrier network, never
    surfaced as an API error Brevo (or therefore RECON) can detect. This
    provider only guards against a completely UNCONFIGURED sender; it cannot
    verify DLT registration itself, and callers must never read a successful
    submission here as a guarantee of delivery to an Indian handset.
    """
    name = "BREVO_SMS"
    _API_URL = "https://api.brevo.com/v3/transactionalSMS/send"

    def send(self, *, to: str, subject: str, body: str,
              template_id: Optional[str] = None, template_vars: Optional[dict] = None) -> ProviderResult:
        if not settings.BREVO_API_KEY:
            return ProviderResult(ok=False, provider=self.name, error_code="NOT_CONFIGURED",
                                  error_message="BREVO_API_KEY is not set.")
        if not settings.BREVO_SMS_SENDER:
            return ProviderResult(ok=False, provider=self.name, error_code="NOT_CONFIGURED",
                                  error_message="BREVO_SMS_SENDER is not set — a DLT-registered "
                                                "sender/header is required before Brevo SMS can send.")
        recipient = _normalize_phone_for_brevo(to)
        if not recipient:
            return ProviderResult(ok=False, provider=self.name, error_code="INVALID_PHONE",
                                  error_message="No usable recipient phone number after normalization.")

        payload: Dict[str, Any] = {
            "sender": settings.BREVO_SMS_SENDER,
            "recipient": recipient,
            "content": body,
            "type": "transactional",
        }
        headers = {"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(self._API_URL, json=payload, headers=headers)
        except httpx.HTTPError:
            return ProviderResult(ok=False, provider=self.name, error_code="TRANSPORT_ERROR",
                                  error_message="Brevo SMS API unreachable.")

        if resp.status_code in (401, 403):
            # Never log the response body — it can echo request/key context.
            logger.warning("Brevo SMS API rejected the request: HTTP %s", resp.status_code)
            return ProviderResult(ok=False, provider=self.name, error_code="BREVO_AUTH_ERROR",
                                  error_message="Brevo rejected the API key.")
        if resp.status_code >= 400:
            logger.warning("Brevo SMS API error: HTTP %s", resp.status_code)
            return ProviderResult(ok=False, provider=self.name, error_code=f"HTTP_{resp.status_code}",
                                  error_message="Brevo SMS API rejected the request.")
        try:
            resp_payload = resp.json()
        except ValueError:
            resp_payload = {}
        # A successful submission means Brevo ACCEPTED the request — never
        # DELIVERED, which only a real delivery confirmation could claim.
        # SMS has no delivery webhook in this phase; status stops at SENT.
        return ProviderResult(ok=True, status="SENT", provider=self.name,
                              provider_message_id=_extract_provider_message_id(resp_payload))


class BrevoWhatsAppProvider(CommunicationProvider):
    """
    Real Brevo transactional WhatsApp — POST https://api.brevo.com/v3/whatsapp/sendMessage,
    `api-key` header auth — see developers.brevo.com/docs/whatsapp-messages.
    Brevo requires a pre-approved templateId (created in Brevo's dashboard
    under Campaigns > WhatsApp) for any message; this provider NEVER sends
    free text — the caller resolves template_id via
    settings.resolved_whatsapp_template() (Brevo-sourced when
    RECON_COMMUNICATIONS_MODE=real — see config.py), and this provider
    refuses to send without one, the same "no unapproved free text" contract
    WebhookWhatsAppProvider already enforces.
    """
    name = "BREVO_WHATSAPP"
    _API_URL = "https://api.brevo.com/v3/whatsapp/sendMessage"

    def send(self, *, to: str, subject: str, body: str,
              template_id: Optional[str] = None, template_vars: Optional[dict] = None) -> ProviderResult:
        if not settings.BREVO_API_KEY:
            return ProviderResult(ok=False, provider=self.name, error_code="NOT_CONFIGURED",
                                  error_message="BREVO_API_KEY is not set.")
        if not settings.BREVO_WHATSAPP_SENDER:
            return ProviderResult(ok=False, provider=self.name, error_code="NOT_CONFIGURED",
                                  error_message="BREVO_WHATSAPP_SENDER is not set.")
        if not template_id:
            return ProviderResult(ok=False, provider=self.name, error_code="TEMPLATE_NOT_CONFIGURED",
                                  error_message="No Brevo WhatsApp templateId is configured for this "
                                                "message type (BREVO_WHATSAPP_TEMPLATE_IDS) — refusing "
                                                "to send unapproved free text as a template message.")
        recipient = _normalize_phone_for_brevo(to)
        if not recipient:
            return ProviderResult(ok=False, provider=self.name, error_code="INVALID_PHONE",
                                  error_message="No usable recipient phone number after normalization.")

        # Brevo's documented templateId is numeric; RECON stores it as a
        # string (same key=value convention as WHATSAPP_TEMPLATE_IDS) — best-
        # effort int conversion, falling back to the raw string rather than
        # failing the send over a formatting difference.
        resolved_template: Any = template_id
        try:
            resolved_template = int(template_id)
        except (TypeError, ValueError):
            pass

        payload: Dict[str, Any] = {
            "contactNumbers": [recipient],
            "senderNumber": settings.BREVO_WHATSAPP_SENDER,
            "templateId": resolved_template,
        }
        if template_vars:
            payload["params"] = template_vars

        headers = {"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(self._API_URL, json=payload, headers=headers)
        except httpx.HTTPError:
            return ProviderResult(ok=False, provider=self.name, error_code="TRANSPORT_ERROR",
                                  error_message="Brevo WhatsApp API unreachable.")

        if resp.status_code in (401, 403):
            logger.warning("Brevo WhatsApp API rejected the request: HTTP %s", resp.status_code)
            return ProviderResult(ok=False, provider=self.name, error_code="BREVO_AUTH_ERROR",
                                  error_message="Brevo rejected the API key.")
        if resp.status_code >= 400:
            logger.warning("Brevo WhatsApp API error: HTTP %s", resp.status_code)
            return ProviderResult(ok=False, provider=self.name, error_code=f"HTTP_{resp.status_code}",
                                  error_message="Brevo WhatsApp API rejected the request.")
        try:
            resp_payload = resp.json()
        except ValueError:
            resp_payload = {}
        return ProviderResult(ok=True, status="SENT", provider=self.name,
                              provider_message_id=_extract_provider_message_id(resp_payload))


_FAKE = {"EMAIL": FakeEmailProvider, "SMS": FakeSMSProvider, "WHATSAPP": FakeWhatsAppProvider}
_REAL = {"EMAIL": BrevoEmailProvider, "SMS": BrevoSmsProvider, "WHATSAPP": BrevoWhatsAppProvider}


def get_communication_provider(channel: str) -> CommunicationProvider:
    registry = _FAKE if settings.RECON_COMMUNICATIONS_MODE != "real" else _REAL
    cls = registry.get(channel.upper())
    if cls is None:
        raise ValueError(f"Unknown communication channel: {channel}")
    return cls()
