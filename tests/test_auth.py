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
