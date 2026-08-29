"""
RECON OS — Event Schemas

Pydantic schemas for revenue events.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class RevenueEventBase(BaseModel):
    razorpay_event_id: str
    event_type: str
    source: str = "razorpay"
    processing_status: str = "received"
    error_message: Optional[str] = None


class RevenueEventCreate(RevenueEventBase):
    merchant_id: UUID
    raw_payload: Dict[str, Any]
    normalized_data: Optional[Dict[str, Any]] = None


class RevenueEventResponse(RevenueEventBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    raw_payload: Dict[str, Any]
    normalized_data: Optional[Dict[str, Any]] = None
    received_at: datetime
    processed_at: Optional[datetime] = None
    created_at: datetime


class RevenueEventListResponse(BaseModel):
    items: list[RevenueEventResponse]
    total: int
    page: int
    limit: int
