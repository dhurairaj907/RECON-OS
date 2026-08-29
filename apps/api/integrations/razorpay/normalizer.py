"""
RECON OS — Razorpay Event Normalizer

Transforms raw, diverse Razorpay webhook payloads into a standardized
internal dictionary structure used across RECON OS.

Phase 3 adds (additive) extraction of the `payment_link` entity so
`payment_link.paid` events can be correlated to a RECON recovery action via
`reference_id` / payment link id.
"""

from decimal import Decimal
from typing import Any, Dict, Optional


def normalize_razorpay_event(raw_payload: Dict[str, Any], event_id_override: Optional[str] = None) -> Dict[str, Any]:
    """
    Normalizes a Razorpay webhook JSON payload into a standard RECON OS event structure.
    """
    event_type = raw_payload.get("event", "unknown")
    payload_wrapper = raw_payload.get("payload", {}) or {}

    # Extract payment entity if present
    payment_entity: Dict[str, Any] = {}
    if "payment" in payload_wrapper and isinstance(payload_wrapper["payment"], dict):
        payment_entity = payload_wrapper["payment"].get("entity", {}) or {}
    elif "order" in payload_wrapper and isinstance(payload_wrapper["order"], dict):
        payment_entity = payload_wrapper["order"].get("entity", {}) or {}

    # Extract payment_link entity if present (Phase 3)
    payment_link_entity: Dict[str, Any] = {}
    if "payment_link" in payload_wrapper and isinstance(payload_wrapper["payment_link"], dict):
        payment_link_entity = payload_wrapper["payment_link"].get("entity", {}) or {}

    # Extract event ID
    event_id = (
        event_id_override
        or raw_payload.get("id")
        or raw_payload.get("event_id")
        or f"evt_syn_{payment_entity.get('id') or payment_link_entity.get('id') or 'unknown'}_{raw_payload.get('created_at', '')}"
    )

    # Amount: prefer the payment entity; fall back to the payment link entity
    amount_paise = payment_entity.get("amount")
    if amount_paise is None:
        amount_paise = payment_link_entity.get("amount", 0)
    amount_paise = amount_paise or 0
    amount_inr = Decimal(str(amount_paise)) / Decimal("100") if amount_paise else Decimal("0.00")

    # Customer notes/name handling
    notes = payment_entity.get("notes", {}) or payment_link_entity.get("notes", {}) or {}
    customer_name = notes.get("name") or notes.get("customer_name")

    return {
        "event_type": event_type,
        "razorpay_event_id": event_id,
        "razorpay_payment_id": payment_entity.get("id"),
        "razorpay_order_id": payment_entity.get("order_id"),
        "razorpay_customer_id": payment_entity.get("customer_id"),
        "amount": str(amount_inr),
        "amount_paise": amount_paise,
        "currency": payment_entity.get("currency") or payment_link_entity.get("currency", "INR"),
        "status": payment_entity.get("status", "unknown"),
        "method": payment_entity.get("method"),
        "customer_email": payment_entity.get("email"),
        "customer_phone": payment_entity.get("contact"),
        "customer_name": customer_name,
        "error_code": payment_entity.get("error_code"),
        "error_description": payment_entity.get("error_description"),
        "error_reason": payment_entity.get("error_reason"),
        "payment_created_at": payment_entity.get("created_at"),
        # --- Phase 3: payment link fields (None for non-payment-link events) ---
        "razorpay_payment_link_id": payment_link_entity.get("id"),
        "payment_link_reference_id": payment_link_entity.get("reference_id"),
        "payment_link_status": payment_link_entity.get("status"),
        "payment_link_amount": payment_link_entity.get("amount"),
        "payment_link_amount_paid": payment_link_entity.get("amount_paid"),
    }
