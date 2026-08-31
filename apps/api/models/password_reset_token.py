"""
RECON OS — Password Reset Token Model  (Phase 5: Authentication)

Same non-secret-at-rest pattern as Session: only the SHA-256 hash of the raw
reset token is stored. The raw token is never returned in an API response —
see routers/auth.py's forgot-password endpoint, which always responds with a
generic message regardless of whether the email exists.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID_TYPE, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<PasswordResetToken user={self.user_id} expires={self.expires_at}>"
