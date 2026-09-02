"""
RECON OS — Provider-Agnostic Normalized Payment Event Contract

This is the shared shape every provider translator must produce so the
shared event processor (services/event_processor.py) never needs to know
which provider an event came from. Today Razorpay is the only real
implementation (integrations/razorpay/normalizer.py::normalize_razorpay_event),
and this TypedDict is exactly the dict it already returns — this file adds a
type annotation and a documented contract, it does not change any runtime
behavior. A future second provider's translator would return this same
shape; `services/event_processor.py`, `models/revenue_event.py::source`, and
every downstream consumer are already provider-agnostic (source is a free
string, e.g. "razorpay"/"simulator") and require no changes to accept it.

`organization_id`/`merchant_id` are deliberately NOT part of this contract —
per the conceptual pipeline (Provider -> webhook -> auth -> translator ->
normalized event -> shared event processor), a provider translator only ever
sees the provider's own payload and must never be trusted to assert which
RECON organization it belongs to. That resolution happens one layer up, in
the router (see database.resolve_connected_merchant), from the platform's
own connection state — never from anything inside the webhook body.
"""

from typing import Optional, TypedDict


class NormalizedPaymentEvent(TypedDict, total=False):
    event_type: str
    razorpay_event_id: str
    razorpay_payment_id: Optional[str]
    razorpay_order_id: Optional[str]
    razorpay_customer_id: Optional[str]
    amount: str  # Decimal-as-string, e.g. "8499.00"
    amount_paise: int
    currency: str
    status: str
    method: Optional[str]
    customer_email: Optional[str]
    customer_phone: Optional[str]
    customer_name: Optional[str]
    error_code: Optional[str]
    error_description: Optional[str]
    error_reason: Optional[str]
    payment_created_at: Optional[int]
    razorpay_payment_link_id: Optional[str]
    payment_link_reference_id: Optional[str]
    payment_link_status: Optional[str]
    payment_link_amount: Optional[int]
    payment_link_amount_paid: Optional[int]
    # --- Phase 9: refund entity (None for non-refund events) ---
    refund_id: Optional[str]
    refund_amount_paise: Optional[int]
    refund_status: Optional[str]
    # True only for events produced by the explicitly-enabled RECON
    # simulator. A real, signature-verified provider webhook can never set
    # this — see integrations/razorpay/normalizer.py.
    recon_simulated: bool
