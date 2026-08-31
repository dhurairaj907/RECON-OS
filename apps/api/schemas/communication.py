"""
RECON OS — Phase 5: Recovery Communication Schemas
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

CHANNELS = ("EMAIL", "SMS", "WHATSAPP")
MESSAGE_TYPES = (
    "PAYMENT_FAILED", "PAYMENT_RECOVERY", "PAYMENT_LINK_CREATED",
    "PAYMENT_RECOVERED", "RECOVERY_REMINDER",
)


class SendCommunicationRequest(BaseModel):
    channel: str = Field(pattern="^(EMAIL|SMS|WHATSAPP)$")
    message_type: str = Field(
        pattern="^(PAYMENT_FAILED|PAYMENT_RECOVERY|PAYMENT_LINK_CREATED|PAYMENT_RECOVERED|RECOVERY_REMINDER)$"
    )


class CommunicationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    recovery_case_id: str
    recovery_action_id: Optional[str] = None
    channel: str
    message_type: str
    status: str
    provider: Optional[str] = None
    recipient: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    skipped_reason: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None


class CommunicationListResponse(BaseModel):
    items: List[CommunicationResponse] = []
    total: int = 0


class SendCommunicationResponse(BaseModel):
    ok: bool
    message: str
    communication: CommunicationResponse


class SequenceEvaluationResponse(BaseModel):
    """Result of evaluating (not necessarily sending) the next step in the
    automatic recovery communication sequence — see
    services/communications/automation.py. `communication` is None when
    nothing was persisted (e.g. automation is disabled, or the next step
    isn't due yet)."""
    ok: bool
    message: str
    communication: Optional[CommunicationResponse] = None
