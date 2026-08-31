"""
RECON OS — Recovery Communication Model  (Phase 5: Communications)

One row per attempted customer communication (a template render + a provider
send attempt). This is a record of what RECON attempted and what the provider
actually reported — never a claim of delivery the provider didn't make.

Scoped by `merchant_id` — the SAME isolation key every other protected table
(RecoveryAction, AuditLog, Customer, ...) already uses. Since Phase 5 gives
each Organization exactly one Merchant (see database.get_org_merchant),
filtering by the caller's resolved merchant_id is sufficient and keeps the
isolation check identical across every resource, not a second pattern.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Text, String, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class Communication(Base):
    __tablename__ = "communications"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)

    merchant_id = Column(UUID_TYPE, ForeignKey("merchants.id"), nullable=False, index=True)
    recovery_case_id = Column(UUID_TYPE, ForeignKey("recovery_cases.id"), nullable=False, index=True)
    recovery_action_id = Column(UUID_TYPE, ForeignKey("recovery_actions.id"), nullable=True, index=True)
    customer_id = Column(UUID_TYPE, ForeignKey("customers.id"), nullable=True, index=True)

    channel = Column(String(20), nullable=False)          # EMAIL | SMS | WHATSAPP
    message_type = Column(String(40), nullable=False)     # PAYMENT_FAILED | PAYMENT_RECOVERY | ...
    status = Column(String(20), nullable=False, default="QUEUED", index=True)
    # QUEUED | SENDING | SENT | DELIVERED | FAILED | SKIPPED | OPTED_OUT | CANCELLED
    # NOT_CONFIGURED is represented as FAILED + error_code="NOT_CONFIGURED" (see
    # services/communications/providers.py) — one vocabulary, not two states
    # meaning the same thing.

    provider = Column(String(30), nullable=True)           # FAKE_EMAIL | FAKE_SMS | ... | real provider name
    recipient = Column(String(255), nullable=True)          # the email/phone actually targeted
    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=True)

    provider_message_id = Column(String(120), nullable=True)
    error_code = Column(String(60), nullable=True)
    error_message = Column(Text, nullable=True)
    skipped_reason = Column(String(60), nullable=True)     # NO_CONTACT_INFO | OPTED_OUT | DUPLICATE |
                                                            # RATE_LIMITED | NOT_ELIGIBLE | REQUIRES_APPROVAL |
                                                            # CASE_LIMIT_REACHED | CUSTOMER_DAILY_LIMIT_REACHED |
                                                            # SEQUENCE_STOPPED

    # Phase 7 — deterministic dedup key: f"{case_id}:{action_id or 'none'}:{message_type}".
    # Never a timestamp/random UUID (those can't detect a genuine retry). Set
    # on every row (sent AND skipped) for traceability; see
    # services/communications/service.py.
    idempotency_key = Column(String(200), nullable=True, index=True)
    # Phase 7 — the last provider delivery-webhook event id applied to this
    # row, so a replayed/duplicate webhook delivery is a safe no-op.
    last_webhook_event_id = Column(String(120), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    sent_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Communication {self.channel}/{self.message_type} {self.status}>"
