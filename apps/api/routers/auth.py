"""
RECON OS — Authentication Router  (Phase 5: Identity + RBAC)

    POST /api/v1/auth/register          create an organization + admin user
    POST /api/v1/auth/login             start a session
    POST /api/v1/auth/logout            end the current session
    POST /api/v1/auth/forgot-password   always returns a generic response
    POST /api/v1/auth/reset-password    consume a reset token
    GET  /api/v1/auth/me                current user/organization/role

No password is ever returned. No password-reset token is ever returned in a
response — forgot-password responds identically whether or not the email
exists (prevents account enumeration).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from auth import (
    AuthContext,
    create_session,
    destroy_session,
    clear_session_cookie,
    generate_token,
    get_auth_context,
    hash_password,
    hash_token,
    set_session_cookie,
    verify_password,
    ROLE_ADMIN,
)
from config import settings
from database import get_db
from models.audit_log import AuditLog
from models.organization import Organization
from models.password_reset_token import PasswordResetToken
from models.session import Session as SessionModel
from models.user import User
from models.user_organization import UserOrganization
from security import password_reset_rate_limit
from services.communications.providers import get_communication_provider
from schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    MessageResponse,
    OrganizationResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)

logger = logging.getLogger("recon.routers.auth")
router = APIRouter(prefix="/auth", tags=["Auth"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _me_response(user: User, organization: Organization, role: str) -> MeResponse:
    return MeResponse(
        user=UserResponse(
            id=str(user.id), email=user.email, is_active=user.is_active,
            created_at=user.created_at, last_login_at=user.last_login_at,
        ),
        organization=OrganizationResponse(
            id=str(organization.id), name=organization.name, created_at=organization.created_at,
        ),
        role=role,
    )


@router.post("/register", response_model=MeResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    """Creates a brand-new Organization with this user as its ADMIN. RECON OS
    has no invite flow in this phase — every registration starts a new org."""
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    organization = Organization(name=payload.organization_name)
    db.add(organization)
    db.flush()

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()

    membership = UserOrganization(user_id=user.id, organization_id=organization.id, role=ROLE_ADMIN)
    db.add(membership)
    db.commit()
    db.refresh(user)
    db.refresh(organization)

    raw_token = create_session(db, user)
    set_session_cookie(response, raw_token)
    logger.info("Registered user %s with new organization %s", user.email, organization.name)
    return _me_response(user, organization, ROLE_ADMIN)


@router.post("/login", response_model=MeResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    generic_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise generic_error

    membership = db.query(UserOrganization).filter(UserOrganization.user_id == user.id).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is not associated with an organization.")
    organization = db.query(Organization).filter(Organization.id == membership.organization_id).first()

    user.last_login_at = _now()
    db.commit()

    raw_token = create_session(db, user)
    set_session_cookie(response, raw_token)
    return _me_response(user, organization, membership.role)


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    # Succeeds even with an already-invalid/expired cookie — logging out
    # never needs to raise 401 for "already logged out".
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if raw_token:
        destroy_session(db, raw_token)
    clear_session_cookie(response)
    return MessageResponse(ok=True, message="Logged out.")


@router.post("/forgot-password", response_model=MessageResponse, dependencies=[Depends(password_reset_rate_limit)])
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    ALWAYS returns the same generic response, whether or not the email
    exists — prevents account enumeration. The raw reset token is NEVER
    included in this (or any) API response.

    Delivery: when RECON_COMMUNICATIONS_MODE=real, the reset link is sent via
    the real configured email provider and the raw token is never logged.
    In "fake" mode (default — dev/test), the token is logged server-side only
    (never returned to the client) since no real provider is configured to
    deliver it — this is the same deterministic local-dev mechanism Phase 5
    established, unchanged in production mode.
    """
    generic = MessageResponse(ok=True, message="If that email exists, a password reset link has been sent.")

    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not user.is_active:
        return generic

    raw_token = generate_token()
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=_now() + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRY_MINUTES),
    ))
    db.commit()

    reset_link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={raw_token}"

    # Resolve the user's own organization/merchant purely to attach an audit
    # entry — never trusted from the request, and this is the ONLY purpose:
    # password-reset email delivery previously had NO persisted record at
    # all (it called the provider directly, bypassing the Communication/
    # audit trail every other RECON message goes through), which is exactly
    # why a delivery problem could go completely unobserved. This does not
    # create a Communication row (a password reset isn't a recovery-case
    # communication and has no case/action/customer to attach one to) — it
    # adds the missing AUDIT record so "did RECON even try to send this" is
    # always answerable.
    membership = db.query(UserOrganization).filter(UserOrganization.user_id == user.id).first()
    merchant_id = None
    if membership is not None:
        from database import get_org_merchant
        org = db.query(Organization).filter(Organization.id == membership.organization_id).first()
        if org is not None:
            merchant_id = get_org_merchant(db, org).id

    if settings.RECON_COMMUNICATIONS_MODE == "real":
        provider = get_communication_provider("EMAIL")
        result = provider.send(
            to=user.email,
            subject="Reset your RECON OS password",
            body=(
                f"Use this link to reset your RECON OS password: {reset_link}\n\n"
                f"This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRY_MINUTES} minutes and "
                f"can only be used once. If you didn't request this, you can ignore this email."
            ),
        )
        # Never log the raw token in real mode — only whether delivery was
        # accepted, and never reveal that to the caller (account enumeration).
        if not result.ok:
            logger.warning("Password reset email could not be sent for %s: %s", user.email, result.error_code)
        else:
            logger.info("Password reset email sent for %s via %s", user.email, result.provider)
        if merchant_id is not None:
            db.add(AuditLog(
                merchant_id=merchant_id, actor="AUTH_SERVICE",
                action="PASSWORD_RESET_EMAIL_SENT" if result.ok else "PASSWORD_RESET_EMAIL_FAILED",
                detail=(f"Password reset email {'sent' if result.ok else 'failed'} for {user.email} "
                       f"via {result.provider or 'SMTP_EMAIL'}"
                       + (f" ({result.error_code})" if not result.ok else "")),
                metadata_json={"provider": result.provider, "error_code": result.error_code},
            ))
            db.commit()
    else:
        # Dev-safe: fake mode only, logged server-side only, never returned to the client.
        logger.info("[DEV] Password reset requested for %s — reset token (dev-log only, fake mode): %s",
                   user.email, raw_token)
        if merchant_id is not None:
            db.add(AuditLog(
                merchant_id=merchant_id, actor="AUTH_SERVICE", action="PASSWORD_RESET_EMAIL_SENT",
                detail=f"Password reset requested for {user.email} (FAKE mode — no real email sent)",
                metadata_json={"provider": "FAKE_EMAIL", "mode": "fake"},
            ))
            db.commit()

    return generic


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(payload.token)
    reset_row = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()

    invalid = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")
    if reset_row is None or reset_row.used_at is not None:
        raise invalid
    expires_at = reset_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _now():
        raise invalid

    user = db.query(User).filter(User.id == reset_row.user_id).first()
    if user is None:
        raise invalid

    user.password_hash = hash_password(payload.new_password)
    reset_row.used_at = _now()
    # A password reset invalidates every existing session for this user.
    db.query(SessionModel).filter(SessionModel.user_id == user.id).delete()
    db.commit()

    logger.info("Password reset completed for %s", user.email)
    return MessageResponse(ok=True, message="Password has been reset. Please log in again.")


@router.get("/me", response_model=MeResponse)
def me(ctx: AuthContext = Depends(get_auth_context)):
    return _me_response(ctx.user, ctx.organization, ctx.role)
