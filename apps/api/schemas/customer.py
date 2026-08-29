"""
RECON OS — Customer Schemas

Pydantic schemas for customer profiles and payment aggregates.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class CustomerBase(BaseModel):
    razorpay_customer_id: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    total_payment_amount: Decimal
    successful_payment_count: int
    failed_payment_count: int
    last_payment_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    total: int
    page: int
    limit: int
