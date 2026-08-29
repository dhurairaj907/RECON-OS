"""
RECON OS — Payment Schemas

Pydantic schemas for payments.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class PaymentBase(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: Optional[str] = None
    amount: Decimal
    amount_paise: int
    currency: str = "INR"
    status: str
    method: Optional[str] = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    error_reason: Optional[str] = None


class PaymentResponse(PaymentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    customer_id: Optional[UUID] = None
    razorpay_data: Optional[Dict[str, Any]] = None
    razorpay_created_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    total: int
    page: int
    limit: int
