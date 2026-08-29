"""
RECON OS — Customer Model
"""

import uuid
from sqlalchemy import Column, String, Integer, Numeric, DateTime, Index, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID_TYPE, ForeignKey("merchants.id"), nullable=False)

    # External identifiers
    razorpay_customer_id = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    name = Column(String(255), nullable=True)

    # Payment aggregates (updated on each event)
    total_payment_amount = Column(Numeric(14, 2), default=0, nullable=False)
    successful_payment_count = Column(Integer, default=0, nullable=False)
    failed_payment_count = Column(Integer, default=0, nullable=False)
    last_payment_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    merchant = relationship("Merchant", back_populates="customers")
    payments = relationship("Payment", back_populates="customer", lazy="dynamic")
    recovery_cases = relationship("RecoveryCase", back_populates="customer", lazy="dynamic")

    __table_args__ = (
        Index("ix_customer_merchant_email", "merchant_id", "email"),
        Index("ix_customer_razorpay_id", "razorpay_customer_id"),
    )

    def __repr__(self):
        return f"<Customer {self.email or self.phone or self.id}>"
