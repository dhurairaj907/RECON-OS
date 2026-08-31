"""
RECON OS — Phase 5: Authentication, Sessions, and RBAC

Password hashing: stdlib PBKDF2-HMAC-SHA256 (no new dependency), 260k
iterations, a random 16-byte salt per password. Format:
    pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
Never store or return a plaintext password.

Sessions: an opaque random token is handed to the browser ONLY as an
httponly cookie. The server stores just its SHA-256 hash (see models.Session)
— a database read alone can never yield a usable session token. Session
expiration is enforced on every request in `get_auth_context`.

Authorization: `AuthContext` binds (user, organization, role) resolved
PURELY from the validated session — an organization id supplied by the
client is never trusted anywhere in this module or in the routers that use
it. `require_role(*roles)` is the server-side enforcement point; the
frontend's own role checks are UX only.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DBSession

from config import settings
from database import get_db
from models.organization import Organization
from models.session import Session as SessionModel
from models.user import User
from models.user_organization import UserOrganization

logger = logging.getLogger("recon.auth")

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
_PBKDF2_ITERATIONS = 260_000
_PBKDF2_ALGO = "sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iterations_s, salt_hex, hash_hex = stored_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    computed = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(computed, expected)


# ---------------------------------------------------------------------------
# Opaque token helpers (sessions + password-reset tokens share this pattern)
# ---------------------------------------------------------------------------
def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def create_session(db: DBSession, user: User) -> str:
    """Persists a new Session (hash only) and returns the RAW token — the raw
    value is never stored and must only ever be handed back once, as a cookie."""
    raw_token = generate_token()
    session_row = SessionModel(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=_now() + timedelta(hours=settings.SESSION_EXPIRY_HOURS),
    )
    db.add(session_row)
    db.commit()
    return raw_token


def destroy_session(db: DBSession, raw_token: str) -> None:
    token_hash = hash_token(raw_token)
    db.query(SessionModel).filter(SessionModel.token_hash == token_hash).delete()
    db.commit()


def set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=settings.SESSION_EXPIRY_HOURS * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")


# ---------------------------------------------------------------------------
# Request-scoped auth context
# ---------------------------------------------------------------------------
@dataclass
class AuthContext:
    user: User
    organization: Organization
    role: str


_SESSION_EXPIRED_DETAIL = "Session expired or invalid. Please log in again."


def get_auth_context(request: Request, db: DBSession = Depends(get_db)) -> AuthContext:
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_EXPIRED_DETAIL)

    token_hash = hash_token(raw_token)
    session_row = db.query(SessionModel).filter(SessionModel.token_hash == token_hash).first()
    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_EXPIRED_DETAIL)

    expires_at = session_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _now():
        db.delete(session_row)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_EXPIRED_DETAIL)

    user = db.query(User).filter(User.id == session_row.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_EXPIRED_DETAIL)

    membership = db.query(UserOrganization).filter(UserOrganization.user_id == user.id).first()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not associated with an organization.",
        )
    organization = db.query(Organization).filter(Organization.id == membership.organization_id).first()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization not found.")

    return AuthContext(user=user, organization=organization, role=membership.role)


ROLE_ADMIN = "ADMIN"
ROLE_OPERATOR = "OPERATOR"
ROLE_APPROVER = "APPROVER"
ROLE_VIEWER = "VIEWER"
ALL_ROLES = (ROLE_ADMIN, ROLE_OPERATOR, ROLE_APPROVER, ROLE_VIEWER)


def require_role(*allowed_roles: str):
    """
    Server-side authorization gate. ADMIN always passes (all organization
    permissions). Any authenticated role otherwise passes only if it's in
    `allowed_roles` — this is the ONLY place role checks happen; the
    frontend's own checks never substitute for this.
    """

    def _dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.role != ROLE_ADMIN and ctx.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {ctx.role} is not permitted to perform this action.",
            )
        return ctx

    return _dependency


def seed_dev_admin(db: DBSession) -> None:
    """
    Local-development-only deterministic login, gated behind
    RECON_DEV_SEED_ADMIN (default False). Creates ONE real user — a properly
    hashed password, a real Organization, a real ADMIN membership — attached
    to the existing default organization/merchant so it can immediately see
    the pre-existing recon_dev.db data. This is a convenience seed, not an
    authentication bypass: the account still has to log in normally.
    """
    if not settings.RECON_DEV_SEED_ADMIN:
        return
    if not settings.RECON_DEV_ADMIN_PASSWORD:
        logger.warning("RECON_DEV_SEED_ADMIN is true but RECON_DEV_ADMIN_PASSWORD is unset — skipping seed.")
        return

    existing = db.query(User).filter(User.email == settings.RECON_DEV_ADMIN_EMAIL).first()
    if existing is not None:
        return

    org = db.query(Organization).filter(Organization.name == settings.DEFAULT_ORGANIZATION_NAME).first()
    if org is None:
        org = Organization(name=settings.DEFAULT_ORGANIZATION_NAME)
        db.add(org)
        db.commit()
        db.refresh(org)

    user = User(email=settings.RECON_DEV_ADMIN_EMAIL, password_hash=hash_password(settings.RECON_DEV_ADMIN_PASSWORD))
    db.add(user)
    db.flush()
    db.add(UserOrganization(user_id=user.id, organization_id=org.id, role=ROLE_ADMIN))
    db.commit()
    logger.info("Seeded local-dev admin user %s for organization %s", user.email, org.name)
