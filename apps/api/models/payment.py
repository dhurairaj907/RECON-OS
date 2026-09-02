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

    # Status — raw Razorpay string, unchanged since Phase 1 (still read by
    # every existing consumer; never renamed).
    status = Column(String(50), nullable=False, index=True)
    method = Column(String(50), nullable=True)

    # --- Phase 9: provider-neutral payment lifecycle (additive) -----------
    # PENDING|AUTHORIZED|CAPTURED|SETTLED|FAILED|REFUNDED|PARTIALLY_REFUNDED|
    # DISPUTED|EXPIRED|MISMATCHED — see schemas/reconciliation.py and
    # services/reconciliation.py, the only writer of this column.
    lifecycle_status = Column(String(20), nullable=True, index=True)
    # IN_SYNC|MISMATCH|UNVERIFIED — whether RECON's lifecycle_status agrees
    # with the last authoritative provider evidence seen for this payment.
    reconciliation_status = Column(String(20), nullable=True, default="UNVERIFIED")
    # Cumulative amount refunded across all refund.processed events seen so
    # far for this payment. Never exceeds amount_paise (enforced in
    # services/reconciliation.py, not here).
    refunded_amount_paise = Column(BigInteger, nullable=False, default=0)
    # OPEN|WON|LOST — set from payment.dispute.* events. A dispute never
    # erases recovery history; see services/reconciliation.py.
    dispute_status = Column(String(20), nullable=True)

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
