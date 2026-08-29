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
from schemas.simulator import SimulateEventRequest, SimulateEventResponse
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
