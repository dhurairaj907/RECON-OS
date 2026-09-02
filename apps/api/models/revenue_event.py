"""
RECON OS — Revenue Event Model
"""

import uuid
from sqlalchemy import Boolean, Column, String, Text, DateTime, Index, ForeignKey, JSON, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class RevenueEvent(Base):
    __tablename__ = "revenue_events"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    razorpay_event_id = Column(String(255), unique=True, nullable=False, index=True)
    merchant_id = Column(UUID_TYPE, ForeignKey("merchants.id"), nullable=False)

    event_type = Column(String(100), nullable=False, index=True)
    source = Column(String(50), default="razorpay", nullable=False)

    processing_status = Column(String(50), default="received", nullable=False, index=True)
    error_message = Column(Text, nullable=True)

    raw_payload = Column(JSON_TYPE, nullable=False)
    normalized_data = Column(JSON_TYPE, nullable=True)

    # --- Phase 9: correlation + provenance (additive) ----------------------
    # The resolved payment/order/payment-link id this event is about — used
    # to correlate across Payment/RecoveryCase/RecoveryAction/Communication
    # by a stable provider identifier, never a display/customer name.
    correlation_id = Column(String(255), nullable=True, index=True)
    # True for a real signature-verified webhook; False for the explicit
    # unsigned-dev-mode path; also True for the gated simulator (which is
    # separately marked via normalized_data.recon_simulated — never silently
    # indistinguishable from a real webhook).
    signature_verified = Column(Boolean, nullable=True)

    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    merchant = relationship("Merchant", back_populates="revenue_events")

    __table_args__ = (
        Index("ix_event_type_status", "event_type", "processing_status"),
    )

    def __repr__(self):
        return f"<RevenueEvent {self.event_type} {self.processing_status} ({self.razorpay_event_id})>"
