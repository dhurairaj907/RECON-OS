"""
RECON OS — Phase 7: Brevo Transactional Webhook Translator

Pure function: translates Brevo's own transactional-webhook JSON shape into
the generic internal shape the existing delivery-webhook state machine
already understands (provider_message_id / event_id / status). Mirrors
integrations/razorpay/normalizer.py's role — a translation layer, never a
second state machine, never DB access, never a side effect.

Confirmed Brevo transactional webhook fields (developers.brevo.com/docs/
transactional-webhooks): event, email, id, date, ts, message-id, ts_event,
ts_epoch, subject, tags.

Event -> RECON status mapping — justified by what each event actually means,
never a blanket "anything but delivered is FAILED":

    delivered   -> "delivered"  terminal, confirmed success
    hardBounce  -> "failed"     terminal — the mailbox does not exist
    blocked     -> "failed"     terminal — Brevo refused to attempt delivery
                                 (e.g. a suppression-list hit)
    invalid     -> "failed"     terminal — the address itself is invalid
    softBounce  -> None         TRANSIENT — Brevo retries; a later `delivered`
                                 or `hardBounce` may still follow
    deferred    -> None         TRANSIENT — temporary delay, Brevo retries
    spam        -> None         the message WAS delivered; this is a
                                 post-delivery complaint, not a delivery
                                 failure. RECON's Communication state machine
                                 has no "complaint" state, so status is left
                                 exactly as it was rather than mis-recorded
                                 as FAILED
    (anything else) -> None     unknown/future event — acknowledged, never
                                 guessed at

`status=None` means "acknowledge this event but do not transition
Communication.status" — the caller (routers/communication_webhooks.py)
still records it against the row for visibility, it just never fabricates a
FAILED/DELIVERED it can't justify.
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict

_TERMINAL_FAILURE_EVENTS = {"hardBounce", "blocked", "invalid"}


class BrevoTranslation(TypedDict):
    provider_message_id: Optional[str]
    event_id: Optional[str]
    status: Optional[str]          # "delivered" | "failed" | None
    raw_event: str
    error_reason: Optional[str]


def _canonical_message_id(value: Any) -> Optional[str]:
    """Strips RFC 5322 angle brackets and surrounding whitespace so a
    Message-ID compares equal regardless of which form either side sends it
    in — never invents a value; returns None if there's nothing usable."""
    if not value:
        return None
    v = str(value).strip()
    if v.startswith("<") and v.endswith(">"):
        v = v[1:-1]
    return v or None


def translate_brevo_event(raw_payload: dict[str, Any]) -> BrevoTranslation:
    raw_event = str(raw_payload.get("event") or "").strip()
    message_id = _canonical_message_id(raw_payload.get("message-id"))

    # Brevo's own numeric event id + its event timestamp make a stable,
    # provider-issued dedup key — never a RECON-invented timestamp/UUID.
    brevo_id = raw_payload.get("id")
    ts_event = raw_payload.get("ts_event") or raw_payload.get("ts")
    event_id = f"brevo:{brevo_id}:{ts_event}" if brevo_id is not None else None

    if raw_event == "delivered":
        status: Optional[str] = "delivered"
    elif raw_event in _TERMINAL_FAILURE_EVENTS:
        status = "failed"
    else:
        status = None

    return BrevoTranslation(
        provider_message_id=message_id,
        event_id=event_id,
        status=status,
        raw_event=raw_event,
        error_reason=raw_event if status == "failed" else None,
    )
