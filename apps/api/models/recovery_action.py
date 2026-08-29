"""
RECON OS — Recovery Action Model  (Phase 3: ACT)

One row per (recovery_case, action_type) recovery attempt. Additive — does not
touch the Phase 1/2 schema. Idempotency is enforced at the DB level via unique
`idempotency_key` and unique `reference_id`.

NEVER stores: Razorpay key id/secret, webhook secret, auth headers, or full raw
provider responses. Only normalised result fields.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import backref, relationship
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)

    recovery_case_id = Column(
        UUID_TYPE, ForeignKey("recovery_cases.id"), nullable=False, index=True
    )
    merchant_id = Column(UUID_TYPE, ForeignKey("merchants.id"), nullable=False)

    action_type = Column(String(40), nullable=False)          # CREATE_PAYMENT_LINK
    action_version = Column(Integer, nullable=False, default=1)

    status = Column(String(30), nullable=False, default="PROPOSED", index=True)
    outcome = Column(String(20), nullable=False, default="PENDING", index=True)

    # Idempotency — deterministic keys, unique at the DB level
    idempotency_key = Column(String(160), nullable=False, unique=True, index=True)
    reference_id = Column(String(80), nullable=False, unique=True, index=True)

    # Decision snapshot (display / audit only — the executor re-checks live)
    strategy_action = Column(String(30), nullable=True)
    policy_verdict = Column(String(20), nullable=True)
    policy_json = Column(JSON_TYPE, nullable=True)

    # Money
    amount = Column(Numeric(14, 2), nullable=False)
    amount_paise = Column(BigInteger, nullable=False)
    currency = Column(String(10), nullable=False, default="INR")
    recovered_amount = Column(Numeric(14, 2), nullable=False, default=0)

    # Provider (Razorpay) — normalised fields only
    provider = Column(String(30), nullable=False, default="RAZORPAY")
    provider_action_id = Column(String(120), nullable=True, index=True)   # plink_xxx
    provider_status = Column(String(40), nullable=True)                   # created|paid|expired|cancelled
    payment_link_url = Column(Text, nullable=True)                        # public short_url
    result_json = Column(JSON_TYPE, nullable=True)                        # normalised: id, short_url, status, reference_id, amount

    # Failure / block info
    blocked_reason = Column(String(60), nullable=True)
    error_code = Column(String(60), nullable=True)
    error_message = Column(Text, nullable=True)

    # Verification — the webhook event that confirmed recovery (double-count guard)
    verifying_event_id = Column(String(255), nullable=True)

    # Lifecycle timestamps
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    recovery_case = relationship(
        "RecoveryCase",
        backref=backref("recovery_actions", lazy="dynamic",
                        order_by="desc(RecoveryAction.created_at)"),
    )

    __table_args__ = (
        Index("ix_recovery_action_case_type", "recovery_case_id", "action_type"),
        Index("ix_recovery_action_merchant_status", "merchant_id", "status"),
        Index("ix_recovery_action_outcome", "merchant_id", "outcome"),
    )

    def __repr__(self):
        return (
            f"<RecoveryAction {self.reference_id} {self.action_type} "
            f"{self.status}/{self.outcome}>"
        )
