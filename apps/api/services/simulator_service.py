"""
RECON OS — Event Simulator Service

Generates realistic Razorpay webhook payloads and feeds them directly
into the standard event ingestion pipeline.
"""

import logging
import time
import uuid
from decimal import Decimal
from typing import Tuple

from sqlalchemy.orm import Session

from models.merchant import Merchant
from models.revenue_event import RevenueEvent
from models.recovery_case import RecoveryCase
from models.recovery_action import RecoveryAction
from schemas.simulator import (
    SimulateEventRequest,
    SimulateEventResponse,
    SimulatePaymentLinkPaidRequest,
)
from services.event_processor import process_inbound_event

logger = logging.getLogger("recon.services.simulator")


def simulate_event(db: Session, request: SimulateEventRequest, merchant_id: uuid.UUID) -> SimulateEventResponse:
    """
    Constructs a synthetic Razorpay payload and executes it via process_inbound_event.
    """
    timestamp = int(time.time())
    random_suffix = uuid.uuid4().hex[:8]
    payment_id = f"pay_sim_{random_suffix}"
    order_id = f"order_sim_{random_suffix}"
    event_id = f"evt_sim_{random_suffix}"

    amount_paise = int(request.amount * 100)
    is_failed = request.event_type == "payment.failed"
    status = "failed" if is_failed else ("captured" if request.event_type == "payment.captured" else "authorized")

    # Build realistic Razorpay JSON payload
    raw_payload = {
        "entity": "event",
        "account_id": "acc_recon_demo",
        "event": request.event_type,
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": amount_paise,
                    "currency": "INR",
                    "status": status,
                    "order_id": order_id,
                    "invoice_id": None,
                    "international": False,
                    "method": request.payment_method,
                    "amount_refunded": 0,
                    "refund_status": None,
                    "captured": status == "captured",
                    "description": f"Simulated transaction ({request.customer_name})",
                    "card_id": None,
                    "bank": None,
                    "wallet": None,
                    "vpa": f"{request.customer_email.split('@')[0]}@upi" if request.payment_method == "upi" else None,
                    "email": request.customer_email,
                    "contact": request.customer_phone or "+919876543210",
                    "customer_id": f"cust_sim_{random_suffix[:6]}",
                    "notes": {
                        "name": request.customer_name,
                        "simulation": "true",
                    },
                    "fee": int(amount_paise * 0.02) if status == "captured" else None,
                    "tax": int(amount_paise * 0.0036) if status == "captured" else None,
                    "error_code": request.failure_code if is_failed else None,
                    "error_description": request.error_description if is_failed else None,
                    "error_source": "customer" if is_failed else None,
                    "error_step": "payment_authentication" if is_failed else None,
                    "error_reason": request.failure_reason if is_failed else None,
                    "acquirer_data": {},
                    "created_at": timestamp,
                }
            }
        },
        "created_at": timestamp,
    }

    # Execute through the standard event processing service
    event, case = process_inbound_event(
        db=db,
        raw_payload=raw_payload,
        merchant_id=merchant_id,
        source="simulator",
        event_id_override=event_id,
    )

    msg = f"Simulated '{request.event_type}' processed successfully."
    if case:
        msg += f" Recovery case {case.case_number} created with ₹{case.amount_at_risk} at risk."

    return SimulateEventResponse(
        success=True,
        event_id=str(event.id),
        razorpay_event_id=event.razorpay_event_id,
        razorpay_payment_id=payment_id,
        event_type=event.event_type,
        processing_status=event.processing_status,
        case_number=case.case_number if case else None,
        message=msg,
    )


def simulate_payment_link_paid(
    db: Session,
    request: SimulatePaymentLinkPaidRequest,
    merchant_id: uuid.UUID,
) -> SimulateEventResponse:
    """
    Phase 3 demo helper: build a realistic `payment_link.paid` Razorpay payload
    for an executed RECON action and run it through the real event pipeline
    (which triggers deterministic outcome verification).
    """
    q = db.query(RecoveryAction).filter(RecoveryAction.merchant_id == merchant_id)
    action = None
    if request.action_id:
        try:
            action = q.filter(RecoveryAction.id == uuid.UUID(str(request.action_id))).first()
        except ValueError:
            action = None
    if action is None and request.reference_id:
        action = q.filter(RecoveryAction.reference_id == request.reference_id).first()
    if action is None:
        raise ValueError("No RECON action found for the supplied action_id / reference_id")
    if not action.provider_action_id:
        raise ValueError(
            "Action has no Payment Link yet — execute the action before simulating payment"
        )

    case = db.query(RecoveryCase).filter(RecoveryCase.id == action.recovery_case_id).first()
    customer = case.customer if case else None

    amount = Decimal(request.amount) if request.amount is not None else Decimal(action.amount or 0)
    amount_paise = int((amount * Decimal("100")).to_integral_value())

    ts = int(time.time())
    suffix = uuid.uuid4().hex[:10]
    event_id = f"evt_plinkpaid_{suffix}"
    pay_id = f"pay_plink_{suffix}"

    raw_payload = {
        "entity": "event",
        "account_id": "acc_recon_demo",
        "event": "payment_link.paid",
        "contains": ["payment_link", "payment"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": action.provider_action_id,
                    "entity": "payment_link",
                    "reference_id": action.reference_id,
                    "amount": amount_paise,
                    "amount_paid": amount_paise,
                    "currency": action.currency or "INR",
                    "status": "paid",
                    "description": f"RECON OS revenue recovery — {case.case_number if case else ''}",
                    "short_url": action.payment_link_url,
                    "created_at": ts,
                    "notes": {"recon_reference_id": action.reference_id},
                }
            },
            "payment": {
                "entity": {
                    "id": pay_id,
                    "entity": "payment",
                    "amount": amount_paise,
                    "currency": action.currency or "INR",
                    "status": "captured",
                    "method": "upi",
                    "captured": True,
                    "email": customer.email if customer else None,
                    "contact": customer.phone if customer else None,
                    "notes": {"recon_reference_id": action.reference_id},
                    "created_at": ts,
                }
            },
        },
        "created_at": ts,
    }

    event, resolved_case = process_inbound_event(
        db=db,
        raw_payload=raw_payload,
        merchant_id=merchant_id,
        source="simulator",
        event_id_override=event_id,
    )

    db.refresh(action)
    msg = (
        f"Simulated payment_link.paid for {action.reference_id}. "
        f"Outcome: {action.outcome}."
    )

    return SimulateEventResponse(
        success=True,
        event_id=str(event.id),
        razorpay_event_id=event.razorpay_event_id,
        razorpay_payment_id=pay_id,
        event_type=event.event_type,
        processing_status=event.processing_status,
        case_number=(resolved_case.case_number if resolved_case else (case.case_number if case else None)),
        message=msg,
    )
