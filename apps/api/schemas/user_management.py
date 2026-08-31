"""RECON OS — Phase 5: minimal user/role management schemas (ADMIN only)."""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class OrgUserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class OrgUserListResponse(BaseModel):
    items: List[OrgUserResponse] = []
    total: int = 0


class UpdateUserRoleRequest(BaseModel):
    role: str = Field(pattern="^(ADMIN|OPERATOR|APPROVER|VIEWER)$")
