"""
RECON OS — Audit Log Model
"""

import uuid
from sqlalchemy import Column, String, Text, DateTime, Index, ForeignKey, JSON, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID_TYPE, ForeignKey("merchants.id"), nullable=False)
    recovery_case_id = Column(UUID_TYPE, ForeignKey("recovery_cases.id"), nullable=True)

    actor = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False, index=True)
    detail = Column(Text, nullable=False)
    metadata_json = Column(JSON_TYPE, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    recovery_case = relationship("RecoveryCase", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_action_time", "action", "created_at"),
    )

    def __repr__(self):
        return f"<AuditLog {self.actor}:{self.action} at {self.created_at}>"
