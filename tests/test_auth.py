"""
RECON OS — Phase 5: Authentication tests.

Covers registration, password hashing, login, logout, session expiration,
and the password reset flow. Uses `unauthenticated_client` (no auto-login)
since these tests exercise the auth boundary itself.
"""

from datetime import datetime, timedelta, timezone

from auth import hash_password, verify_password
from config import settings
from models.password_reset_token import PasswordResetToken
from models.session import Session as SessionModel
from models.user import User


def test_password_is_hashed_not_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_register_creates_org_and_admin(unauthenticated_client):
    res = unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "founder@newco.test", "password": "SuperSecret123!", "organization_name": "NewCo Inc",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["user"]["email"] == "founder@newco.test"
    assert body["organization"]["name"] == "NewCo Inc"
    assert body["role"] == "ADMIN"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
    # A session cookie was actually issued
    assert settings.SESSION_COOKIE_NAME in unauthenticated_client.cookies


def test_register_duplicate_email_rejected(unauthenticated_client):
    body = {"email": "dupe@newco.test", "password": "SuperSecret123!", "organization_name": "Org A"}
    r1 = unauthenticated_client.post("/api/v1/auth/register", json=body)
    assert r1.status_code == 201
    r2 = unauthenticated_client.post("/api/v1/auth/register", json={**body, "organization_name": "Org B"})
    assert r2.status_code == 409


def test_login_success(unauthenticated_client, db_session):
    db_session.add(User(email="loginuser@recon.test", password_hash=hash_password("MyPassword123!")))
    db_session.commit()
    # No org membership yet -> login should 403 (no organization), proving
    # org membership is genuinely required, not assumed.
    res = unauthenticated_client.post("/api/v1/auth/login", json={
        "email": "loginuser@recon.test", "password": "MyPassword123!",
    })
    assert res.status_code == 403


def test_session_cookie_secure_flag_follows_setting(unauthenticated_client, monkeypatch):
    """Deployment-hardening: the session cookie's Secure attribute must
    reflect SESSION_COOKIE_SECURE — off for local HTTP dev (the default),
    on when a deployment explicitly enables it for HTTPS. Never hardcoded
    either way (see auth.py::set_session_cookie)."""
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", False)
    res_dev = unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "secure-flag-dev@recon.test", "password": "SuperSecret123!",
        "organization_name": "Secure Flag Dev Org",
    })
    assert res_dev.status_code == 201, res_dev.text
    cookie_header_dev = res_dev.headers.get("set-cookie", "")
    assert settings.SESSION_COOKIE_NAME in cookie_header_dev
    assert "secure" not in cookie_header_dev.lower()
    assert "httponly" in cookie_header_dev.lower()

    unauthenticated_client.cookies.clear()
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", True)
    res_prod = unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "secure-flag-prod@recon.test", "password": "SuperSecret123!",
        "organization_name": "Secure Flag Prod Org",
    })
    assert res_prod.status_code == 201, res_prod.text
    cookie_header_prod = res_prod.headers.get("set-cookie", "")
    assert "secure" in cookie_header_prod.lower()
    assert "httponly" in cookie_header_prod.lower()


def test_local_dev_cookie_defaults_to_samesite_lax(unauthenticated_client, monkeypatch):
    """Cross-domain hardening: the DEFAULT SameSite policy must remain
    'lax' (unchanged local-dev behavior) unless a deployment explicitly
    opts into 'none' for a cross-site frontend/backend split."""
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "SESSION_COOKIE_SAMESITE", "lax")
    res = unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "samesite-lax-default@recon.test", "password": "SuperSecret123!",
        "organization_name": "SameSite Lax Default Org",
    })
    assert res.status_code == 201, res.text
    cookie_header = res.headers.get("set-cookie", "").lower()
    assert "samesite=lax" in cookie_header
    assert "secure" not in cookie_header, "local HTTP dev must never get a Secure cookie"


def test_cross_domain_production_cookie_is_samesite_none_and_secure(unauthenticated_client, monkeypatch):
    """Cross-domain hardening: a deployment where the frontend (e.g.
    Cloudflare Pages) and backend (e.g. Render) are on different domains
    MUST set SESSION_COOKIE_SAMESITE=none for the browser to send the
    cookie on cross-site API calls at all — and it must come back paired
    with Secure, or the browser drops the cookie outright."""
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "SESSION_COOKIE_SAMESITE", "none")
    res = unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "samesite-none-prod@recon.test", "password": "SuperSecret123!",
        "organization_name": "SameSite None Prod Org",
    })
    assert res.status_code == 201, res.text
    cookie_header = res.headers.get("set-cookie", "").lower()
    assert "samesite=none" in cookie_header
    assert "secure" in cookie_header
    assert "httponly" in cookie_header


def test_samesite_none_forces_secure_even_if_secure_setting_left_false(unauthenticated_client, monkeypatch):
    """Safety guard: SameSite=None without Secure is a cookie the browser
    silently drops entirely — auth.py must never produce that combination,
    even if an operator misconfigures SESSION_COOKIE_SECURE=false while
    setting SESSION_COOKIE_SAMESITE=none. This can only make the cookie
    MORE restrictive than requested, never less."""
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "SESSION_COOKIE_SAMESITE", "none")
    res = unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "samesite-none-misconfigured@recon.test", "password": "SuperSecret123!",
        "organization_name": "SameSite None Misconfigured Org",
    })
    assert res.status_code == 201, res.text
    cookie_header = res.headers.get("set-cookie", "").lower()
    assert "samesite=none" in cookie_header
    assert "secure" in cookie_header, "SameSite=None must always be paired with Secure, regardless of SESSION_COOKIE_SECURE"


def test_invalid_samesite_value_falls_back_to_lax(unauthenticated_client, monkeypatch, caplog):
    """An unrecognized SESSION_COOKIE_SAMESITE value must fail safe to the
    original 'lax' default, not raise or silently produce an invalid
    cookie attribute."""
    monkeypatch.setattr(settings, "SESSION_COOKIE_SAMESITE", "not-a-real-value")
    res = unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "samesite-invalid@recon.test", "password": "SuperSecret123!",
        "organization_name": "SameSite Invalid Org",
    })
    assert res.status_code == 201, res.text
    cookie_header = res.headers.get("set-cookie", "").lower()
    assert "samesite=lax" in cookie_header


def test_clear_session_cookie_matches_set_cookie_attributes(unauthenticated_client, monkeypatch):
    """logout's delete_cookie must use the SAME Secure/SameSite attributes
    the session cookie was actually set with, so browsers reliably clear
    a cross-site (SameSite=None; Secure) cookie on logout too."""
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "SESSION_COOKIE_SAMESITE", "none")
    unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "samesite-logout@recon.test", "password": "SuperSecret123!",
        "organization_name": "SameSite Logout Org",
    })
    res = unauthenticated_client.post("/api/v1/auth/logout")
    assert res.status_code == 200, res.text
    cookie_header = res.headers.get("set-cookie", "").lower()
    assert "samesite=none" in cookie_header
    assert "secure" in cookie_header


def test_login_invalid_credentials(unauthenticated_client):
    unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "realuser@recon.test", "password": "RealPassword123!", "organization_name": "RealOrg",
    })
    unauthenticated_client.cookies.clear()
    bad_pw = unauthenticated_client.post("/api/v1/auth/login", json={
        "email": "realuser@recon.test", "password": "WrongPassword!",
    })
    assert bad_pw.status_code == 401
    unknown = unauthenticated_client.post("/api/v1/auth/login", json={
        "email": "doesnotexist@recon.test", "password": "Whatever123!",
    })
    assert unknown.status_code == 401
    # Both failure modes return the SAME generic detail — no enumeration.
    assert bad_pw.json()["detail"] == unknown.json()["detail"]


def test_unauthenticated_request_is_rejected(unauthenticated_client):
    res = unauthenticated_client.get("/api/v1/dashboard/metrics")
    assert res.status_code == 401


def test_logout_clears_session(unauthenticated_client):
    unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "logoutuser@recon.test", "password": "Password123!", "organization_name": "LogoutOrg",
    })
    assert unauthenticated_client.get("/api/v1/dashboard/metrics").status_code == 200
    logout = unauthenticated_client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    after = unauthenticated_client.get("/api/v1/dashboard/metrics")
    assert after.status_code == 401


def test_logout_is_idempotent(unauthenticated_client):
    # Logging out with no session at all must not error.
    res = unauthenticated_client.post("/api/v1/auth/logout")
    assert res.status_code == 200


def test_session_expiration(unauthenticated_client, db_session):
    reg = unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "expiring@recon.test", "password": "Password123!", "organization_name": "ExpiringOrg",
    })
    assert reg.status_code == 201
    user = db_session.query(User).filter(User.email == "expiring@recon.test").first()
    session_row = db_session.query(SessionModel).filter(SessionModel.user_id == user.id).first()
    session_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    res = unauthenticated_client.get("/api/v1/dashboard/metrics")
    assert res.status_code == 401


def test_forgot_password_generic_response_for_unknown_and_known_email(unauthenticated_client, db_session):
    unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "resetme@recon.test", "password": "OldPassword123!", "organization_name": "ResetOrg",
    })
    known = unauthenticated_client.post("/api/v1/auth/forgot-password", json={"email": "resetme@recon.test"})
    unknown = unauthenticated_client.post("/api/v1/auth/forgot-password", json={"email": "ghost@recon.test"})
    assert known.status_code == 200 and unknown.status_code == 200
    assert known.json() == unknown.json()
    # The raw token is never in the response.
    assert "token" not in known.text.lower().replace("please log in", "")


def test_reset_password_flow(unauthenticated_client, db_session):
    unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "resetflow@recon.test", "password": "OldPassword123!", "organization_name": "ResetFlowOrg",
    })
    user = db_session.query(User).filter(User.email == "resetflow@recon.test").first()

    # Simulate "receiving" the emailed token by reading it server-side (as a
    # real email integration would deliver it) rather than via any API response.
    from auth import generate_token, hash_token
    raw_token = generate_token()
    db_session.add(PasswordResetToken(
        user_id=user.id, token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    ))
    db_session.commit()

    reset = unauthenticated_client.post("/api/v1/auth/reset-password", json={
        "token": raw_token, "new_password": "BrandNewPassword123!",
    })
    assert reset.status_code == 200

    # Old session was invalidated by the reset.
    assert unauthenticated_client.get("/api/v1/dashboard/metrics").status_code == 401

    # New password works; old one doesn't.
    unauthenticated_client.cookies.clear()
    old_login = unauthenticated_client.post("/api/v1/auth/login", json={
        "email": "resetflow@recon.test", "password": "OldPassword123!",
    })
    assert old_login.status_code == 401
    new_login = unauthenticated_client.post("/api/v1/auth/login", json={
        "email": "resetflow@recon.test", "password": "BrandNewPassword123!",
    })
    assert new_login.status_code == 200


def test_reset_password_rejects_reused_token(unauthenticated_client, db_session):
    unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "reuse@recon.test", "password": "Password123!", "organization_name": "ReuseOrg",
    })
    user = db_session.query(User).filter(User.email == "reuse@recon.test").first()
    from auth import generate_token, hash_token
    raw_token = generate_token()
    db_session.add(PasswordResetToken(
        user_id=user.id, token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    ))
    db_session.commit()

    first = unauthenticated_client.post("/api/v1/auth/reset-password", json={
        "token": raw_token, "new_password": "FirstNewPassword123!",
    })
    assert first.status_code == 200
    second = unauthenticated_client.post("/api/v1/auth/reset-password", json={
        "token": raw_token, "new_password": "SecondNewPassword123!",
    })
    assert second.status_code == 400


def test_reset_password_rejects_expired_token(unauthenticated_client, db_session):
    unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "expiredtoken@recon.test", "password": "Password123!", "organization_name": "ExpiredTokenOrg",
    })
    user = db_session.query(User).filter(User.email == "expiredtoken@recon.test").first()
    from auth import generate_token, hash_token
    raw_token = generate_token()
    db_session.add(PasswordResetToken(
        user_id=user.id, token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),   # already expired
    ))
    db_session.commit()

    res = unauthenticated_client.post("/api/v1/auth/reset-password", json={
        "token": raw_token, "new_password": "WontWork123!",
    })
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower() or "invalid" in res.json()["detail"].lower()

    # The password must be genuinely unchanged.
    unauthenticated_client.cookies.clear()
    login = unauthenticated_client.post("/api/v1/auth/login", json={
        "email": "expiredtoken@recon.test", "password": "Password123!",
    })
    assert login.status_code == 200


def test_forgot_password_persists_token_with_correct_expiry(unauthenticated_client, db_session):
    """forgot-password must create a REAL PasswordResetToken row (hash only,
    never the raw token) with an expiry matching
    PASSWORD_RESET_TOKEN_EXPIRY_MINUTES — this is the row reset-password
    later consumes, independent of whether email delivery itself succeeds."""
    unauthenticated_client.post("/api/v1/auth/register", json={
        "email": "tokenpersist@recon.test", "password": "Password123!", "organization_name": "TokenPersistOrg",
    })
    user = db_session.query(User).filter(User.email == "tokenpersist@recon.test").first()

    before = datetime.now(timezone.utc)
    res = unauthenticated_client.post("/api/v1/auth/forgot-password", json={"email": "tokenpersist@recon.test"})
    assert res.status_code == 200

    row = (
        db_session.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == user.id)
        .order_by(PasswordResetToken.id.desc())
        .first()
    )
    assert row is not None
    assert row.used_at is None
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    expected = before + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRY_MINUTES)
    assert abs((expires_at - expected).total_seconds()) < 5
