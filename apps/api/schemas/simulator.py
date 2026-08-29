"""
RECON OS — Simulator Schemas

Pydantic schemas for generating simulated payment events.
"""

from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class SimulateEventRequest(BaseModel):
    event_type: str = Field(..., description="payment.failed | payment.captured | payment.authorized")
    customer_name: str = Field(default="Demo Customer", description="Customer full name")
    customer_email: str = Field(default="demo@reconos.io", description="Customer email")
    customer_phone: Optional[str] = Field(default="+919876543210", description="Customer phone")
    amount: Decimal = Field(default=Decimal("4999.00"), description="Amount in INR")
    payment_method: str = Field(default="upi", description="upi | card | netbanking | wallet")
    failure_code: Optional[str] = Field(default="BAD_REQUEST_ERROR", description="Error code if payment failed")
    failure_reason: Optional[str] = Field(default="payment_failed", description="Error reason")
    error_description: Optional[str] = Field(default="Payment processing failed due to bank timeout", description="Human-readable error description")


class SimulateEventResponse(BaseModel):
    success: bool
    event_id: str
    razorpay_event_id: str
    razorpay_payment_id: str
    event_type: str
    processing_status: str
    case_number: Optional[str] = None
    message: str
