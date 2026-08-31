"""
RECON OS — Phase 5: Authentication Schemas

Never includes a password or password_hash field on any response model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Deliberately a plain `str` + manual check rather than pydantic's EmailStr —
# the `email-validator` package isn't an existing project dependency and a
# full RFC validator isn't required here (Do NOT introduce unnecessary
# dependencies). This only rejects obviously-malformed input.
_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _validate_email(v: str) -> str:
    import re
    v = v.strip().lower()
    if not re.match(_EMAIL_RE, v):
        raise ValueError("Invalid email address")
    return v


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    organization_name: str = Field(min_length=1, max_length=255)

    _validate = field_validator("email")(_validate_email)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    _validate = field_validator("email")(_validate_email)


class ForgotPasswordRequest(BaseModel):
    email: str

    _validate = field_validator("email")(_validate_email)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class OrganizationResponse(BaseModel):
    id: str
    name: str
    created_at: datetime


class MeResponse(BaseModel):
    user: UserResponse
    organization: OrganizationResponse
    role: str


class MessageResponse(BaseModel):
    ok: bool
    message: str
