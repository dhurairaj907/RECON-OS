"""
RECON OS — Evaluation harness: isolated database + shared scenario helpers.

Each scenario runs against its own fresh in-memory SQLite database (mirroring
tests/conftest.py's isolation, but self-contained so this package can run
outside pytest) and drives the REAL pipeline: process_inbound_event ->
run_intelligence -> get_or_create_action -> execute_action -> approval /
unknown-verification / reconcile. Nothing here re-implements product logic.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import Base
from models.merchant import Merchant
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from models.payment import Payment
from services.actions.approval import approve_action, reject_action
from services.actions.common import to_paise
from services.actions.executor import execute_action
from services.actions.proposal import get_or_create_action
from services.actions.reconcile import reconcile_action
from services.actions.unknown import verify_unknown_action
from services.event_processor import process_inbound_event
from services.intelligence.orchestrator import run_intelligence


@contextmanager
def isolated_db():
    """A fresh SQLite in-memory database + seeded merchant, torn down on exit."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    prior_engine, prior_session_local = database.engine, database.SessionLocal
    database.engine, database.SessionLocal = engine, SessionLocal
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    merchant = Merchant(name="Evaluation Merchant")
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    try:
        yield db, merchant
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        database.engine, database.SessionLocal = prior_engine, prior_session_local


def payment_failed_payload(
    *, event_id="evt_eval", payment_id="pay_eval", amount_paise=499900,
    method="upi", email="eval@recon.test", contact="+919800000000",
    customer_id="cust_eval", customer_name="Eval Customer",
    error_code="BAD_REQUEST_ERROR", error_reason="payment_failed",
    error_description="UPI handle authorization timeout on customer app",
):
    return {
        "entity": "event", "event": "payment.failed", "contains": ["payment"],
        "id": event_id,
        "payload": {"payment": {"entity": {
            "id": payment_id, "amount": amount_paise, "currency": "INR", "status": "failed",
            "order_id": "order_" + payment_id, "method": method,
            "email": email, "contact": contact,
            "customer_id": customer_id, "notes": {"name": customer_name},
            "error_code": error_code, "error_reason": error_reason,
            "error_description": error_description,
            "created_at": 1700000000,
        }}}, "created_at": 1700000000,
    }


def payment_captured_payload(*, event_id, payment_id, amount_paise, order_id=None, customer_id="cust_eval"):
    return {
        "entity": "event", "event": "payment.captured", "contains": ["payment"],
        "id": event_id,
        "payload": {"payment": {"entity": {
            "id": payment_id, "amount": amount_paise, "currency": "INR", "status": "captured",
            "order_id": order_id or ("order_" + payment_id), "method": "upi",
            "email": "eval@recon.test", "customer_id": customer_id,
            "notes": {}, "created_at": 1700000100,
        }}}, "created_at": 1700000100,
    }


def create_case(db, merchant, payload) -> RecoveryCase:
    _, case = process_inbound_event(db=db, raw_payload=payload, merchant_id=merchant.id)
    return case


def analyze(db, case) -> RecoveryCase:
    run_intelligence(db, case.id, trigger="evaluation")
    db.refresh(case)
    return case


def propose(db, case) -> RecoveryAction | None:
    action, proposal = get_or_create_action(db, case)
    return action


def set_payment_status(db, case, status: str) -> None:
    payment = db.query(Payment).filter_by(id=case.payment_id).first()
    if payment is not None:
        payment.status = status
        db.commit()
