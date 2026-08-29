"""
RECON OS — Phase 2: Context Builder

Assembles a deterministic `CaseContext` from real database rows. No writes, no
side effects, no invented data. If a fact is not in the database it is left at
its neutral default.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models.customer import Customer
from models.payment import Payment
from models.recovery_case import RecoveryCase
from schemas.intelligence import CaseContext
from services.intelligence.weights import amount_band

logger = logging.getLogger("recon.services.intelligence.context")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def build_case_context(db: Session, case: RecoveryCase) -> CaseContext:
    """
    Build a point-in-time CaseContext for a RecoveryCase.

    Deterministic given the database state at call time. The only time-dependent
    field is `hours_since_failure`, which is a genuine feature (a recovery case
    that has been open for a week behaves differently from one opened a minute
    ago) and is consumed by the prediction scorecard only in coarse, monotonic
    buckets.
    """
    payment: Payment | None = None
    if case.payment_id is not None:
        payment = db.query(Payment).filter(Payment.id == case.payment_id).first()

    customer: Customer | None = None
    if case.customer_id is not None:
        customer = db.query(Customer).filter(Customer.id == case.customer_id).first()

    # --- customer aggregates -------------------------------------------------
    successful = int(customer.successful_payment_count) if customer else 0
    failed = int(customer.failed_payment_count) if customer else 0
    lifetime = Decimal(customer.total_payment_amount) if customer else Decimal("0.00")
    settled = successful + failed
    success_rate = (successful / settled) if settled > 0 else 0.0
    has_history = settled >= 2

    # --- prior recovery activity for this customer (excludes current case) --
    prev_cases = 0
    prev_resolved = 0
    prev_attempts = 0
    if case.customer_id is not None:
        others = (
            db.query(RecoveryCase)
            .filter(
                RecoveryCase.customer_id == case.customer_id,
                RecoveryCase.id != case.id,
            )
            .all()
        )
        prev_cases = len(others)
        prev_resolved = sum(1 for c in others if (c.status or "").upper() == "RESOLVED")
        prev_attempts = sum(int(c.attempt_count or 0) for c in others)

    # --- timing ------------------------------------------------------------
    opened_at = _aware(case.opened_at)
    hours_since_failure = 0.0
    if opened_at is not None:
        hours_since_failure = max(
            0.0, (_utcnow() - opened_at).total_seconds() / 3600.0
        )

    amount = Decimal(case.amount_at_risk or 0)

    return CaseContext(
        case_id=str(case.id),
        case_number=case.case_number,
        case_status=case.status or "DETECTED",
        amount=amount,
        currency=case.currency or "INR",
        attempt_count=int(case.attempt_count or 0),
        max_attempts=int(case.max_attempts or 3),
        opened_at=opened_at,
        hours_since_failure=round(hours_since_failure, 3),
        payment_id=(payment.razorpay_payment_id if payment else None),
        payment_status=(payment.status if payment else None),
        payment_method=(payment.method if payment else None),
        failure_code=case.failure_code or (payment.error_code if payment else None),
        failure_reason=(payment.error_reason if payment else None),
        failure_description=(
            case.failure_reason
            or (payment.error_description if payment else None)
        ),
        customer_id=(str(case.customer_id) if case.customer_id else None),
        customer_name=(customer.name if customer else None),
        customer_successful_payments=successful,
        customer_failed_payments=failed,
        customer_lifetime_amount=lifetime,
        customer_success_rate=round(success_rate, 4),
        customer_has_history=has_history,
        previous_recovery_cases=prev_cases,
        previous_resolved_cases=prev_resolved,
        previous_recovery_attempts=prev_attempts,
        customer_contacts_last_24h=0,  # Phase 3 will populate real contact history
        amount_band=amount_band(amount),
    )
