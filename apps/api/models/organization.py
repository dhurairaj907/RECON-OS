"""
RECON OS — Organization Model  (Phase 5: Identity + RBAC)

The tenant/account boundary above `Merchant`. Every authenticated User belongs
to exactly one Organization (via `UserOrganization`); every `Merchant` (and
therefore every payment/customer/case/action/communication hanging off it)
belongs to exactly one Organization. This is the isolation boundary — see
`auth.get_current_organization` and `database.get_org_merchant`.
"""

import uuid

from sqlalchemy import Column, DateTime, String, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self):
        return f"<Organization {self.name} ({self.id})>"
