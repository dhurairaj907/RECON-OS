"""
RECON OS — Recovery Case Schemas

Pydantic schemas for recovery cases and case lists.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from schemas.customer import CustomerResponse
from schemas.payment import PaymentResponse
from schemas.intelligence import IntelligenceSummary


class RecoveryCaseBase(BaseModel):
    case_number: str
    amount_at_risk: Decimal
    amount_recovered: Decimal = Decimal("0.00")
    currency: str = "INR"
    failure_reason: Optional[str] = None
    failure_code: Optional[str] = None
    status: str = "DETECTED"
    priority: str = "MEDIUM"
    attempt_count: int = 0
    max_attempts: int = 3


class RecoveryCaseResponse(RecoveryCaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    customer_id: Optional[UUID] = None
    payment_id: Optional[UUID] = None
    opened_at: datetime
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    customer: Optional[CustomerResponse] = None
    payment: Optional[PaymentResponse] = None
    # Phase 2 (THINK): populated by the API layer when an analysis exists.
    # Optional & additive — Phase 1 consumers are unaffected.
    intelligence: Optional[IntelligenceSummary] = None


class RecoveryCaseListResponse(BaseModel):
    items: list[RecoveryCaseResponse]
    total: int
    page: int
    limit: int
