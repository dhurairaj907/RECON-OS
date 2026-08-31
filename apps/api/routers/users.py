"""
RECON OS — Users Router  (Phase 5: RBAC — ADMIN only)

    GET   /api/v1/users              list this organization's members
    PATCH /api/v1/users/{id}/role    change a member's role

Organization-scoped like every other resource: a target user id from another
organization is never resolvable here, regardless of what the caller sends.
No invite-a-new-teammate flow in this phase — new members currently only
arrive via /auth/register, which always creates a NEW organization. See
README limitations.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import AuthContext, ROLE_ADMIN, require_role
from database import get_db
from models.user import User
from models.user_organization import UserOrganization
from schemas.user_management import OrgUserListResponse, OrgUserResponse, UpdateUserRoleRequest

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=OrgUserListResponse)
def list_org_users(ctx: AuthContext = Depends(require_role(ROLE_ADMIN)), db: Session = Depends(get_db)):
    rows = (
        db.query(UserOrganization, User)
        .join(User, User.id == UserOrganization.user_id)
        .filter(UserOrganization.organization_id == ctx.organization.id)
        .all()
    )
    items = [
        OrgUserResponse(
            id=str(u.id), email=u.email, role=m.role, is_active=u.is_active,
            created_at=u.created_at, last_login_at=u.last_login_at,
        )
        for m, u in rows
    ]
    return OrgUserListResponse(items=items, total=len(items))


@router.patch("/{user_id}/role", response_model=OrgUserResponse)
def update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    ctx: AuthContext = Depends(require_role(ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user id")

    membership = (
        db.query(UserOrganization)
        .filter(UserOrganization.user_id == uid, UserOrganization.organization_id == ctx.organization.id)
        .first()
    )
    if membership is None:
        # Deliberately identical 404 whether the user doesn't exist or belongs
        # to a different organization — never confirms cross-org existence.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    membership.role = payload.role
    db.commit()

    user = db.query(User).filter(User.id == uid).first()
    return OrgUserResponse(
        id=str(user.id), email=user.email, role=membership.role, is_active=user.is_active,
        created_at=user.created_at, last_login_at=user.last_login_at,
    )
