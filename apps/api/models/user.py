"""
RECON OS — User Model  (Phase 5: Identity + RBAC)

Password is NEVER stored in plaintext — only a salted PBKDF2-HMAC-SHA256 hash
(see auth.py). No password value is ever returned in an API response.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, String, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<User {self.email}>"
