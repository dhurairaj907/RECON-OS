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
from config import settings

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

    Base.metadata.create_all(bind=engine)
    # Seed default merchant
    db = TestingSessionLocal()
    merchant = Merchant(name="Test Merchant")
    db.add(merchant)
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
