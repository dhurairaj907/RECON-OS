"""
RECON OS — Recovery Case Model
"""

import uuid
from sqlalchemy import Column, String, Integer, Numeric, Text, DateTime, Index, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    case_number = Column(String(50), unique=True, nullable=False, index=True)

    merchant_id = Column(UUID_TYPE, ForeignKey("merchants.id"), nullable=False)
    customer_id = Column(UUID_TYPE, ForeignKey("customers.id"), nullable=True)
    payment_id = Column(UUID_TYPE, ForeignKey("payments.id"), nullable=True)

    amount_at_risk = Column(Numeric(14, 2), nullable=False)
    amount_recovered = Column(Numeric(14, 2), default=0, nullable=False)
    currency = Column(String(10), default="INR", nullable=False)

    failure_reason = Column(Text, nullable=True)
    failure_code = Column(String(255), nullable=True)

    status = Column(String(50), default="DETECTED", nullable=False, index=True)
    priority = Column(String(20), default="MEDIUM", nullable=False, index=True)

    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)

    opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    merchant = relationship("Merchant", back_populates="recovery_cases")
    customer = relationship("Customer", back_populates="recovery_cases")
    payment = relationship("Payment")
    audit_logs = relationship("AuditLog", back_populates="recovery_case", lazy="dynamic")

    __table_args__ = (
        Index("ix_case_status_priority", "status", "priority"),
    )

    def __repr__(self):
        return f"<RecoveryCase {self.case_number} [{self.status}] ₹{self.amount_at_risk}>"
