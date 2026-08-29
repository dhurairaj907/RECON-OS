"""
RECON OS — Razorpay Event Normalizer

Transforms raw, diverse Razorpay webhook payloads into a standardized
internal dictionary structure used across RECON OS.
"""

from decimal import Decimal
from typing import Any, Dict, Optional


def normalize_razorpay_event(raw_payload: Dict[str, Any], event_id_override: Optional[str] = None) -> Dict[str, Any]:
    """
    Normalizes a Razorpay webhook JSON payload into a standard RECON OS event structure.

    Args:
        raw_payload: Parsed JSON dict of the Razorpay webhook payload.
        event_id_override: Optional ID if provided by the webhook headers or simulator.

    Returns:
        Dict[str, Any] with standard fields:
            - event_type: str
            - razorpay_event_id: str
            - razorpay_payment_id: Optional[str]
            - razorpay_order_id: Optional[str]
            - razorpay_customer_id: Optional[str]
            - amount: Decimal (in INR)
            - amount_paise: int
            - currency: str
            - status: str
            - method: Optional[str]
            - customer_email: Optional[str]
            - customer_phone: Optional[str]
            - customer_name: Optional[str]
            - error_code: Optional[str]
            - error_description: Optional[str]
            - error_reason: Optional[str]
            - payment_created_at: Optional[int] (unix timestamp)
    """
    event_type = raw_payload.get("event", "unknown")
    payload_wrapper = raw_payload.get("payload", {})

    # Extract payment entity if present
    payment_entity = {}
    if "payment" in payload_wrapper and isinstance(payload_wrapper["payment"], dict):
        payment_entity = payload_wrapper["payment"].get("entity", {})
    elif "order" in payload_wrapper and isinstance(payload_wrapper["order"], dict):
        # In order events, payment entity might be inside order or contains
        payment_entity = payload_wrapper["order"].get("entity", {})

    # Extract event ID
    event_id = (
        event_id_override
        or raw_payload.get("id")
        or raw_payload.get("event_id")
        or f"evt_syn_{payment_entity.get('id', 'unknown')}_{raw_payload.get('created_at', '')}"
    )

    amount_paise = payment_entity.get("amount", 0)
    # Convert paise to INR (100 paise = 1 INR)
    amount_inr = Decimal(str(amount_paise)) / Decimal("100") if amount_paise else Decimal("0.00")

    # Customer notes/name handling
    notes = payment_entity.get("notes", {}) or {}
    customer_name = notes.get("name") or notes.get("customer_name")

    return {
        "event_type": event_type,
        "razorpay_event_id": event_id,
        "razorpay_payment_id": payment_entity.get("id"),
        "razorpay_order_id": payment_entity.get("order_id"),
        "razorpay_customer_id": payment_entity.get("customer_id"),
        "amount": str(amount_inr),
        "amount_paise": amount_paise,
        "currency": payment_entity.get("currency", "INR"),
        "status": payment_entity.get("status", "unknown"),
        "method": payment_entity.get("method"),
        "customer_email": payment_entity.get("email"),
        "customer_phone": payment_entity.get("contact"),
        "customer_name": customer_name,
        "error_code": payment_entity.get("error_code"),
        "error_description": payment_entity.get("error_description"),
        "error_reason": payment_entity.get("error_reason"),
        "payment_created_at": payment_entity.get("created_at"),
    }
