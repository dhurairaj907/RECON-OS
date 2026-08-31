"""
RECON OS — Test Configuration & Fixtures

Uses an SQLite in-memory database for isolated, lightning-fast tests.
"""

import hmac
import hashlib
import json
import pytest
import sys
from pathlib import Path
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add apps/api to python path
API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
sys.path.insert(0, str(API_DIR))

import database
from database import Base, get_db
from main import app
from models.merchant import Merchant
from models.organization import Organization
from models.user import User
from models.user_organization import UserOrganization
from config import settings
from auth import ROLE_ADMIN, hash_password

# Known credentials for the auto-authenticated default test user — every
# `client`-fixture test logs in as this ADMIN user of the default test
# organization, so existing (pre-Phase-5) endpoint tests keep working exactly
# as before without individually wiring up auth. Cross-organization tests
# create a SECOND, separate organization/user explicitly (see
# test_organization_isolation.py).
TEST_USER_EMAIL = "test-admin@recon.test"
TEST_USER_PASSWORD = "TestPassword123!"

# Test DB Engine
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_database(monkeypatch):
    """Create all tables before each test and drop them after."""
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    # The simulator is a test/demo utility — enable it for the suite. Individual
    # tests turn it off explicitly to assert the 403 gate.
    monkeypatch.setattr(settings, "RECON_SIMULATOR_ENABLED", True)
    # Starlette's TestClient reports a fixed fake client host for every request,
    # so the per-IP rate limiter would otherwise bucket the entire test suite
    # together. Individual tests exercise the limiter directly (test_security.py)
    # against a real, non-zero limit.
    monkeypatch.setattr(settings, "RECON_RATE_LIMIT_PER_MINUTE", 0)
    # Same reasoning for the Phase 7 password-reset limiter — a fixed
    # TestClient host would otherwise bucket the whole suite together.
    # Individual tests exercise this limiter directly (test_security.py).
    monkeypatch.setattr(settings, "PASSWORD_RESET_RATE_LIMIT_PER_HOUR", 0)

    Base.metadata.create_all(bind=engine)
    # Seed default org + merchant + admin user for every test in the suite.
    db = TestingSessionLocal()
    organization = Organization(name="Test Organization")
    db.add(organization)
    db.flush()
    merchant = Merchant(name="Test Merchant", organization_id=organization.id)
    db.add(merchant)
    user = User(email=TEST_USER_EMAIL, password_hash=hash_password(TEST_USER_PASSWORD))
    db.add(user)
    db.flush()
    db.add(UserOrganization(user_id=user.id, organization_id=organization.id, role=ROLE_ADMIN))
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a transactional database session for tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session, monkeypatch):
    """FastAPI TestClient with overridden get_db dependency."""
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        # Auto-authenticate as the default test ADMIN so every pre-existing
        # (pre-Phase-5) endpoint test keeps working unmodified — real
        # login, real session cookie, not an auth bypass.
        login = test_client.post("/api/v1/auth/login", json={
            "email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD,
        })
        assert login.status_code == 200, login.text
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client(db_session, monkeypatch):
    """Same TestClient wiring as `client`, but WITHOUT logging in — for
    testing the auth gate itself."""
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def webhook_secret():
    return "test_webhook_secret_key_12345"


@pytest.fixture
def make_signature(webhook_secret):
    """Helper to generate HMAC-SHA256 signature for test payloads."""
    def _generate(raw_bytes: bytes, secret: str = webhook_secret) -> str:
        return hmac.new(
            key=secret.encode("utf-8"),
            msg=raw_bytes,
            digestmod=hashlib.sha256
        ).hexdigest()
    return _generate


@pytest.fixture
def sample_payment_failed_payload():
    return {
        "entity": "event",
        "account_id": "acc_test123",
        "event": "payment.failed",
        "contains": ["payment"],
        "id": "evt_test_failed_001",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_001",
                    "entity": "payment",
                    "amount": 849900,  # ₹8,499.00
                    "currency": "INR",
                    "status": "failed",
                    "order_id": "order_test_001",
                    "method": "upi",
                    "email": "customer@recon.test",
                    "contact": "+919876543210",
                    "customer_id": "cust_test_001",
                    "notes": {"name": "ABC Corp"},
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Payment processing failed due to bank timeout",
                    "error_reason": "payment_failed",
                    "created_at": 1620000000,
                }
            }
        },
        "created_at": 1620000000,
    }


@pytest.fixture
def sample_payment_captured_payload():
    return {
        "entity": "event",
        "account_id": "acc_test123",
        "event": "payment.captured",
        "contains": ["payment"],
        "id": "evt_test_captured_001",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_001",
                    "entity": "payment",
                    "amount": 849900,
                    "currency": "INR",
                    "status": "captured",
                    "order_id": "order_test_001",
                    "method": "upi",
                    "email": "customer@recon.test",
                    "contact": "+919876543210",
                    "customer_id": "cust_test_001",
                    "notes": {"name": "ABC Corp"},
                    "created_at": 1620000000,
                }
            }
        },
        "created_at": 1620000050,
    }
