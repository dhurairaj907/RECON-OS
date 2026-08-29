"""
RECON OS — Event Processor Service Tests

Validates:
1. Normalization of payment failure and capture payloads
2. Customer aggregate calculations
3. Payment record state transitions
4. Recovery case creation & resolution
5. Out-of-order event protection
"""

from decimal import Decimal
from models.merchant import Merchant
from models.customer import Customer
from models.payment import Payment
from models.recovery_case import RecoveryCase
from models.revenue_event import RevenueEvent
from services.event_processor import process_inbound_event


def test_payment_failed_creates_recovery_case(db_session, sample_payment_failed_payload):
    merchant = db_session.query(Merchant).first()

    event, case = process_inbound_event(
        db=db_session,
        raw_payload=sample_payment_failed_payload,
        merchant_id=merchant.id,
        source="razorpay",
    )

    assert event is not None
    assert event.event_type == "payment.failed"
    assert event.processing_status == "processed"

    assert case is not None
    assert case.amount_at_risk == Decimal("8499.00")
    assert case.status == "DETECTED"
    assert case.priority == "MEDIUM"  # 8499 is between 2500 and 10000

    # Verify customer aggregates
    customer = db_session.query(Customer).filter_by(email="customer@recon.test").first()
    assert customer is not None
    assert customer.failed_payment_count == 1
    assert customer.successful_payment_count == 0


def test_payment_captured_resolves_open_case(db_session, sample_payment_failed_payload, sample_payment_captured_payload):
    merchant = db_session.query(Merchant).first()

    # Step 1: Payment Fails
    _, case1 = process_inbound_event(
        db=db_session,
        raw_payload=sample_payment_failed_payload,
        merchant_id=merchant.id,
    )
    assert case1.status == "DETECTED"

    # Step 2: Payment Later Succeeded (captured)
    _, case2 = process_inbound_event(
        db=db_session,
        raw_payload=sample_payment_captured_payload,
        merchant_id=merchant.id,
    )

    assert case2 is not None
    assert case2.id == case1.id
    assert case2.status == "RESOLVED"
    assert case2.amount_recovered == Decimal("8499.00")

    # Verify customer aggregates
    customer = db_session.query(Customer).filter_by(email="customer@recon.test").first()
    assert customer.successful_payment_count == 1
    assert customer.total_payment_amount == Decimal("8499.00")


def test_out_of_order_event_protection(db_session, sample_payment_captured_payload, sample_payment_failed_payload):
    """
    If a 'payment.captured' event arrived first, a delayed 'payment.failed' event
    must NOT downgrade the payment status from captured to failed.
    """
    merchant = db_session.query(Merchant).first()

    # First: captured arrives
    process_inbound_event(
        db=db_session,
        raw_payload=sample_payment_captured_payload,
        merchant_id=merchant.id,
    )
    payment = db_session.query(Payment).filter_by(razorpay_payment_id="pay_test_001").first()
    assert payment.status == "captured"

    # Second: out-of-order failed arrives with different event ID
    sample_payment_failed_payload["id"] = "evt_delayed_failed_002"
    process_inbound_event(
        db=db_session,
        raw_payload=sample_payment_failed_payload,
        merchant_id=merchant.id,
    )

    db_session.refresh(payment)
    # Payment must remain captured!
    assert payment.status == "captured"
