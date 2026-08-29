"""
RECON OS — Payment Model
"""

import uuid
from sqlalchemy import Column, String, Integer, BigInteger, Numeric, Text, DateTime, Index, ForeignKey, JSON, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    razorpay_payment_id = Column(String(255), unique=True, nullable=False, index=True)
    merchant_id = Column(UUID_TYPE, ForeignKey("merchants.id"), nullable=False)
    customer_id = Column(UUID_TYPE, ForeignKey("customers.id"), nullable=True)

    # Order reference
    razorpay_order_id = Column(String(255), nullable=True, index=True)

    # Amount
    amount = Column(Numeric(14, 2), nullable=False)
    amount_paise = Column(BigInteger, nullable=False)
    currency = Column(String(10), default="INR", nullable=False)

    # Status
    status = Column(String(50), nullable=False, index=True)
    method = Column(String(50), nullable=True)

    # Failure details
    error_code = Column(String(255), nullable=True)
    error_description = Column(Text, nullable=True)
    error_reason = Column(String(255), nullable=True)

    # Full Razorpay payment entity
    razorpay_data = Column(JSON_TYPE, nullable=True)

    # Timestamps
    razorpay_created_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    merchant = relationship("Merchant", back_populates="payments")
    customer = relationship("Customer", back_populates="payments")

    def __repr__(self):
        return f"<Payment {self.razorpay_payment_id} {self.status} ₹{self.amount}>"
