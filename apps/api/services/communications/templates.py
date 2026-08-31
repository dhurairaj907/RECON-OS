"""
RECON OS — Phase 5: Recovery Message Templates  (server-side only)

Every customer-facing message is rendered here from a fixed template — never
assembled ad hoc in a router, a service, or (especially) the frontend. AI
never generates the message text; it may only recommend which template/
channel to use (see services/communications/service.py:decide_communication).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RenderedMessage:
    subject: str
    body: str
    # The same field values used to render subject/body, exposed separately so
    # a channel that sends structured template variables (e.g. WhatsApp) can
    # use them without re-deriving anything or accepting raw AI-generated text.
    variables: dict


_TEMPLATES = {
    "PAYMENT_FAILED": {
        "subject": "We couldn't process your payment to {organization_name}",
        "body": (
            "Hi {customer_name}, your payment of {currency} {amount} to {organization_name} "
            "could not be completed. No action has been taken yet — we'll follow up shortly "
            "with a way to complete it."
        ),
    },
    "PAYMENT_RECOVERY": {
        "subject": "Complete your payment to {organization_name}",
        "body": (
            "Hi {customer_name}, you can complete your payment of {currency} {amount} to "
            "{organization_name} using this secure link: {payment_link}"
        ),
    },
    "PAYMENT_LINK_CREATED": {
        "subject": "Your payment link for {organization_name} is ready",
        "body": (
            "Hi {customer_name}, here is your secure payment link for {currency} {amount}: "
            "{payment_link}{expiry_clause}"
        ),
    },
    "PAYMENT_RECOVERED": {
        "subject": "Payment received — thank you",
        "body": (
            "Hi {customer_name}, we've received your payment of {currency} {amount} to "
            "{organization_name}. Thank you!"
        ),
    },
    "RECOVERY_REMINDER": {
        "subject": "Reminder: complete your payment to {organization_name}",
        "body": (
            "Hi {customer_name}, this is a reminder that your payment of {currency} {amount} "
            "to {organization_name} is still pending: {payment_link}"
        ),
    },
}

TEMPLATE_NAMES = tuple(_TEMPLATES.keys())


def render_template(
    message_type: str,
    *,
    customer_name: str,
    amount: str,
    currency: str,
    organization_name: str,
    payment_link: Optional[str] = None,
    expiry_time: Optional[str] = None,
) -> RenderedMessage:
    tpl = _TEMPLATES.get(message_type)
    if tpl is None:
        raise ValueError(f"Unknown message template: {message_type}")

    expiry_clause = f" (valid until {expiry_time})" if expiry_time else ""
    fields = dict(
        customer_name=customer_name or "there",
        amount=amount,
        currency=currency,
        organization_name=organization_name,
        payment_link=payment_link or "",
        expiry_clause=expiry_clause,
    )
    return RenderedMessage(
        subject=tpl["subject"].format(**fields),
        body=tpl["body"].format(**fields),
        variables=fields,
    )
