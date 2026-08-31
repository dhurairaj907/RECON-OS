"""
RECON OS — Session Model  (Phase 5: Authentication)

Opaque server-side session. The raw token is handed to the browser ONLY as an
httponly cookie and is NEVER persisted — only its SHA-256 hash is stored, so a
database read alone can never yield a usable session token (see auth.py).
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID_TYPE, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Session user={self.user_id} expires={self.expires_at}>"
