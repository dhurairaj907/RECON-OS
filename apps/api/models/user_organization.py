"""
RECON OS — User/Organization Membership + Role  (Phase 5: RBAC)

One row per (user, organization) — a user belongs to exactly one organization
in this phase (registration always creates a fresh organization), but the
join-table shape leaves room for multi-org membership later without a schema
change. `role` is one of ADMIN | OPERATOR | APPROVER | VIEWER — see auth.py
for the permission checks.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class UserOrganization(Base):
    __tablename__ = "user_organizations"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID_TYPE, ForeignKey("users.id"), nullable=False, index=True)
    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="VIEWER")  # ADMIN|OPERATOR|APPROVER|VIEWER

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_user_organization"),
    )

    def __repr__(self):
        return f"<UserOrganization user={self.user_id} org={self.organization_id} role={self.role}>"
