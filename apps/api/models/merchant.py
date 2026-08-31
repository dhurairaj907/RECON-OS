"""
RECON OS — Merchant Model
"""

import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    # Phase 5: the tenant/isolation boundary above Merchant. Nullable at the
    # column level only because it's added via a lightweight ADD COLUMN
    # migration to an existing table — database.ensure_default_organization()
    # backfills every pre-Phase-5 merchant onto a real Organization at startup.
    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    customers = relationship("Customer", back_populates="merchant", lazy="dynamic")
    payments = relationship("Payment", back_populates="merchant", lazy="dynamic")
    revenue_events = relationship("RevenueEvent", back_populates="merchant", lazy="dynamic")
    recovery_cases = relationship("RecoveryCase", back_populates="merchant", lazy="dynamic")

    def __repr__(self):
        return f"<Merchant {self.name} ({self.id})>"
