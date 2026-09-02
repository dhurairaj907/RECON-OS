"""
RECON OS — Event Processor Service

Core data plane service that handles:
1. Deduplication / Idempotency
2. Customer record lookup / creation and aggregate calculation
3. Payment record creation / status update with ordering safety
4. Recovery Case creation for payment failures (Phase 1 deterministic)
5. Case resolution on successful payment capture
6. Full audit logging
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from models.merchant import Merchant
from models.customer import Customer
from models.payment import Payment
from models.revenue_event import RevenueEvent
from models.recovery_case import RecoveryCase
from models.audit_log import AuditLog
from integrations.razorpay.normalizer import normalize_razorpay_event
from services.reconciliation import reconcile_payment_lifecycle
from config import settings

logger = logging.getLogger("recon.services.event_processor")


def calculate_case_priority(amount: Decimal) -> str:
    """Deterministic priority assignment based on risk amount (Phase 1)."""
    if amount >= Decimal("50000.00"):
        return "CRITICAL"
    elif amount >= Decimal("10000.00"):
        return "HIGH"
    elif amount >= Decimal("2500.00"):
        return "MEDIUM"
    return "LOW"


def generate_case_number(db: Session) -> str:
    """Generates an incremental unique case reference e.g., RC-10001."""
    count = db.query(func.count(RecoveryCase.id)).scalar() or 0
    return f"RC-{10000 + count + 1}"


def process_inbound_event(
    db: Session,
    raw_payload: Dict[str, Any],
    merchant_id: UUID,
    source: str = "razorpay",
    event_id_override: Optional[str] = None,
    signature_verified: Optional[bool] = None,
) -> tuple[RevenueEvent, Optional[RecoveryCase]]:
    """
    Main ingestion & processing pipeline for revenue events.

    `signature_verified`: Phase 9 provenance flag for the event ledger —
    pass True from a caller that already verified an HMAC webhook signature
    (see routers/webhooks.py). Left None for the simulator / evaluation
    harness paths, which never carry a real provider signature.

    Returns:
        tuple[RevenueEvent, Optional[RecoveryCase]]
    """
    # 1. Normalize the payload
    normalized = normalize_razorpay_event(raw_payload, event_id_override=event_id_override)
    event_id = normalized["razorpay_event_id"]
    event_type = normalized["event_type"]
    # Phase 9 — the resolved payment/order/payment-link id this event is
    # about, used to correlate across Payment/RecoveryCase/RecoveryAction/
    # Communication by a stable provider identifier only.
    correlation_id = (
        normalized.get("razorpay_payment_id")
        or normalized.get("razorpay_payment_link_id")
        or normalized.get("razorpay_order_id")
    )

    logger.info(f"Processing event {event_id} of type '{event_type}' from {source}")

    # 2. Check for duplicate event (Idempotency)
    existing_event = db.query(RevenueEvent).filter_by(razorpay_event_id=event_id).first()
    if existing_event:
        logger.info(f"Duplicate event detected: {event_id}. Skipping re-processing.")
        # Log duplicate attempt for audit
        audit = AuditLog(
            merchant_id=merchant_id,
            actor=source.upper(),
            action="DUPLICATE_EVENT_IGNORED",
            detail=f"Ignored duplicate event {event_id} ({event_type})",
            metadata_json={"event_id": event_id, "event_type": event_type}
        )
        db.add(audit)
        db.commit()

        # Find existing case if any
        existing_case = None
        if normalized.get("razorpay_payment_id"):
            payment = db.query(Payment).filter_by(razorpay_payment_id=normalized["razorpay_payment_id"]).first()
            if payment:
                existing_case = db.query(RecoveryCase).filter_by(payment_id=payment.id).first()
        return existing_event, existing_case

    # 3. Persist the RevenueEvent immediately
    revenue_event = RevenueEvent(
        razorpay_event_id=event_id,
        merchant_id=merchant_id,
        event_type=event_type,
        source=source,
        processing_status="processing",
        raw_payload=raw_payload,
        normalized_data=normalized,
        received_at=datetime.now(timezone.utc),
        correlation_id=correlation_id,
        signature_verified=signature_verified,
    )
    db.add(revenue_event)
    db.flush()

    recovery_case = None
    case_was_created = False

    try:
        # 4. Find or create Customer
        customer = None
        email = normalized.get("customer_email")
        phone = normalized.get("customer_phone")
        cust_rzp_id = normalized.get("razorpay_customer_id")
        name = normalized.get("customer_name")

        if email or cust_rzp_id or phone:
            customer_query = db.query(Customer).filter(Customer.merchant_id == merchant_id)
            if cust_rzp_id:
                customer = customer_query.filter(Customer.razorpay_customer_id == cust_rzp_id).first()
            if not customer and email:
                customer = customer_query.filter(Customer.email == email).first()
            if not customer and phone:
                customer = customer_query.filter(Customer.phone == phone).first()

            if not customer:
                customer = Customer(
                    merchant_id=merchant_id,
                    razorpay_customer_id=cust_rzp_id,
                    email=email,
                    phone=phone,
                    name=name or (email.split("@")[0].capitalize() if email else "Customer"),
                    total_payment_amount=Decimal("0.00"),
                    successful_payment_count=0,
                    failed_payment_count=0,
                )
                db.add(customer)
                db.flush()
            else:
                # Update details if new name/phone provided
                if name and not customer.name:
                    customer.name = name
                if phone and not customer.phone:
                    customer.phone = phone
                if cust_rzp_id and not customer.razorpay_customer_id:
                    customer.razorpay_customer_id = cust_rzp_id

        # 5. Find or create/update Payment
        payment_rzp_id = normalized.get("razorpay_payment_id")
        payment = None
        amount_inr = Decimal(normalized.get("amount", "0.00"))
        amount_paise = normalized.get("amount_paise", 0)
        status = normalized.get("status", "unknown")

        if payment_rzp_id:
            payment = db.query(Payment).filter_by(razorpay_payment_id=payment_rzp_id).first()

            # Handle out-of-order webhooks: Do not downgrade a 'captured' payment to 'failed'
            if payment:
                if payment.status == "captured" and status in ("failed", "created", "authorized"):
                    logger.warning(f"Out-of-order event: ignoring status change from captured to {status} for {payment_rzp_id}")
                else:
                    payment.status = status
                    payment.method = normalized.get("method") or payment.method
                    payment.error_code = normalized.get("error_code") or payment.error_code
                    payment.error_description = normalized.get("error_description") or payment.error_description
                    payment.error_reason = normalized.get("error_reason") or payment.error_reason
                    payment.razorpay_data = raw_payload
                    payment.updated_at = datetime.now(timezone.utc)
            else:
                rzp_created_at = None
                if normalized.get("payment_created_at"):
                    try:
                        rzp_created_at = datetime.fromtimestamp(normalized["payment_created_at"], tz=timezone.utc)
                    except Exception:
                        pass

                payment = Payment(
                    razorpay_payment_id=payment_rzp_id,
                    merchant_id=merchant_id,
                    customer_id=customer.id if customer else None,
                    razorpay_order_id=normalized.get("razorpay_order_id"),
                    amount=amount_inr,
                    amount_paise=amount_paise,
                    currency=normalized.get("currency", "INR"),
                    status=status,
                    method=normalized.get("method"),
                    error_code=normalized.get("error_code"),
                    error_description=normalized.get("error_description"),
                    error_reason=normalized.get("error_reason"),
                    razorpay_data=raw_payload,
                    razorpay_created_at=rzp_created_at,
                )
                db.add(payment)
                db.flush()

            # Update customer aggregates
            if customer:
                customer.last_payment_at = datetime.now(timezone.utc)
                if status == "captured":
                    customer.successful_payment_count += 1
                    customer.total_payment_amount += amount_inr
                elif status == "failed":
                    customer.failed_payment_count += 1
                db.flush()

        # 6. Event-specific business logic

        # 6a. Phase 3 (ACT) — Payment Link recovery verification.
        # MUST be checked before the generic "captured" branch: a payment_link.paid
        # event also carries a nested captured payment entity. Handles paid /
        # expired / cancelled. Runs only AFTER signature verification (webhook)
        # or the explicit simulator path.
        _is_payment_link_event = (
            str(event_type).startswith("payment_link.")
            or normalized.get("payment_link_status") is not None
        )
        if _is_payment_link_event:
            try:
                from services.actions.verification import verify_payment_link_recovery
                matched = verify_payment_link_recovery(
                    db, normalized, merchant_id, revenue_event.razorpay_event_id
                )
                if matched is not None:
                    recovery_case = db.query(RecoveryCase).filter(
                        RecoveryCase.id == matched.recovery_case_id
                    ).first()
            except Exception:
                logger.exception(
                    "payment_link event verification failed (non-fatal for Phase 1)"
                )

        # 6b. Phase 8 — reconciliation/mismatch foundation. Checked BEFORE the
        # payment.failed/captured branches below: a dispute webhook's nested
        # payment entity is typically still "captured", which would otherwise
        # be misread by the generic captured-branch as a fresh successful
        # payment. Deliberately conservative per the directive's §9: this
        # never creates a case and never mutates amount_recovered/status —
        # it only records a signal for a human to review. Event names
        # verified against current official Razorpay webhook documentation
        # (razorpay.com/docs/webhooks/refunds/, /docs/webhooks/disputes/).
        elif str(event_type).startswith("refund.") or str(event_type).startswith("payment.dispute."):
            related_case = (
                db.query(RecoveryCase).filter_by(payment_id=payment.id).first()
                if payment else None
            )
            recovery_case = related_case
            kind = "refund" if str(event_type).startswith("refund.") else "dispute"

            # Phase 9 — the payment's own lifecycle/mismatch tracking. A
            # SEPARATE concern from the case-level "was this already
            # RESOLVED" check right below: this only ever touches Payment
            # fields (lifecycle_status, refunded_amount_paise,
            # dispute_status), never RecoveryCase/RecoveryAction.
            if payment:
                reconcile_payment_lifecycle(
                    db, payment, normalized, merchant_id=merchant_id,
                    event_id=event_id,
                    recovery_case_id=related_case.id if related_case else None,
                )

            if related_case is not None and related_case.status == "RESOLVED":
                # Money is moving backward on a case RECON already believes is
                # recovered — exactly the mismatch the directive calls out
                # ("Provider: FAILED, RECON: CAPTURED -> investigate rather
                # than blindly changing revenue"). Recorded, not auto-fixed.
                audit = AuditLog(
                    merchant_id=merchant_id,
                    recovery_case_id=related_case.id,
                    actor=source.upper(),
                    action="PAYMENT_STATE_RECONCILIATION_MISMATCH",
                    detail=(
                        f"{event_type} received for payment {payment_rzp_id} on case "
                        f"{related_case.case_number}, which RECON already marked RESOLVED "
                        f"(amount_recovered=₹{related_case.amount_recovered}). Not "
                        f"automatically reflected in revenue_recovered — review manually."
                    ),
                    metadata_json={
                        "event_id": event_id, "event_type": event_type, "kind": kind,
                        "case_number": related_case.case_number, "payment_id": payment_rzp_id,
                    },
                )
            else:
                audit = AuditLog(
                    merchant_id=merchant_id,
                    recovery_case_id=related_case.id if related_case else None,
                    actor=source.upper(),
                    action="REFUND_EVENT_RECEIVED" if kind == "refund" else "DISPUTE_EVENT_RECEIVED",
                    detail=(
                        f"{event_type} received for payment {payment_rzp_id or 'N/A'} "
                        f"— recorded for review, no automatic state change."
                    ),
                    metadata_json={
                        "event_id": event_id, "event_type": event_type, "kind": kind,
                        "payment_id": payment_rzp_id,
                    },
                )
            db.add(audit)

        elif event_type == "payment.failed" or status == "failed":
            # Check if a recovery case already exists for this payment
            existing_case = db.query(RecoveryCase).filter_by(payment_id=payment.id).first() if payment else None
            if not existing_case:
                case_number = generate_case_number(db)
                priority = calculate_case_priority(amount_inr)
                failure_desc = normalized.get("error_description") or normalized.get("error_reason") or "Payment processing failed"

                recovery_case = RecoveryCase(
                    case_number=case_number,
                    merchant_id=merchant_id,
                    customer_id=customer.id if customer else None,
                    payment_id=payment.id if payment else None,
                    amount_at_risk=amount_inr,
                    amount_recovered=Decimal("0.00"),
                    currency=normalized.get("currency", "INR"),
                    failure_reason=failure_desc,
                    failure_code=normalized.get("error_code"),
                    status="DETECTED",
                    priority=priority,
                    attempt_count=0,
                    max_attempts=3,
                    simulated=bool(normalized.get("recon_simulated", False)),
                )
                db.add(recovery_case)
                db.flush()
                case_was_created = True

                # Audit Log
                audit = AuditLog(
                    merchant_id=merchant_id,
                    recovery_case_id=recovery_case.id,
                    actor="RECON_ENGINE",
                    action="RECOVERY_CASE_CREATED",
                    detail=f"Created recovery case {case_number} for ₹{amount_inr} ({priority} priority) - {failure_desc}",
                    metadata_json={
                        "case_number": case_number,
                        "payment_id": payment_rzp_id,
                        "amount": str(amount_inr),
                        "priority": priority,
                        "error_code": normalized.get("error_code")
                    }
                )
                db.add(audit)
                logger.info(f"Created Recovery Case {case_number} for payment {payment_rzp_id}")
            else:
                recovery_case = existing_case

            # Phase 9 — payment lifecycle tracking, AFTER case resolution
            # above so the audit entry can be correlated to the right case
            # (separate concern: this never touches RecoveryCase itself).
            if payment:
                reconcile_payment_lifecycle(
                    db, payment, normalized, merchant_id=merchant_id, event_id=event_id,
                    recovery_case_id=recovery_case.id if recovery_case else None,
                )

        elif event_type in ("payment.captured", "order.paid") or status == "captured":
            # If payment succeeded, check if there was an open recovery case for it and resolve it
            if payment:
                open_case = db.query(RecoveryCase).filter(
                    RecoveryCase.payment_id == payment.id,
                    RecoveryCase.status.in_(["DETECTED", "OPEN"])
                ).first()

                if open_case:
                    open_case.status = "RESOLVED"
                    open_case.amount_recovered = amount_inr
                    open_case.resolved_at = datetime.now(timezone.utc)
                    recovery_case = open_case

                    audit = AuditLog(
                        merchant_id=merchant_id,
                        recovery_case_id=open_case.id,
                        actor="RECON_ENGINE",
                        action="RECOVERY_CASE_RESOLVED",
                        detail=f"Resolved case {open_case.case_number} via successful capture of ₹{amount_inr}",
                        metadata_json={
                            "case_number": open_case.case_number,
                            "payment_id": payment_rzp_id,
                            "amount_recovered": str(amount_inr)
                        }
                    )
                    db.add(audit)
                    logger.info(f"Resolved Recovery Case {open_case.case_number} on payment capture.")

                # Phase 9 — payment lifecycle tracking, AFTER case resolution
                # above so the audit entry can be correlated to the right
                # case (separate concern: this never touches RecoveryCase).
                reconcile_payment_lifecycle(
                    db, payment, normalized, merchant_id=merchant_id, event_id=event_id,
                    recovery_case_id=open_case.id if open_case else None,
                )

        # 7. Mark event as processed
        revenue_event.processing_status = "processed"
        revenue_event.processed_at = datetime.now(timezone.utc)

        # General Event Audit Log
        event_audit = AuditLog(
            merchant_id=merchant_id,
            recovery_case_id=recovery_case.id if recovery_case else None,
            actor=source.upper(),
            action="EVENT_PROCESSED",
            detail=f"Processed event {event_id} ({event_type}) for payment {payment_rzp_id or 'N/A'}",
            metadata_json={"event_id": event_id, "event_type": event_type, "status": status}
        )
        db.add(event_audit)

        db.commit()
        db.refresh(revenue_event)
        if recovery_case:
            db.refresh(recovery_case)

        # --- Phase 2 (THINK) hook -----------------------------------------
        # Runs ONLY after Phase 1 has fully committed, in its own isolated
        # transaction/session. A Phase 2 failure can never roll back Phase 1
        # or fail the webhook / simulator.
        if case_was_created and recovery_case is not None and settings.INTELLIGENCE_ENABLED:
            new_case_id = recovery_case.id
            try:
                from services.intelligence.orchestrator import run_intelligence_isolated
                run_intelligence_isolated(new_case_id, trigger="pipeline")
            except Exception:
                logger.exception(
                    "Post-commit intelligence run failed for case %s (non-fatal)",
                    new_case_id,
                )

        return revenue_event, recovery_case

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to process event {event_id}: {e}", exc_info=True)
        # Mark event as failed in a new transaction
        try:
            revenue_event.processing_status = "failed"
            revenue_event.error_message = str(e)
            revenue_event.processed_at = datetime.now(timezone.utc)
            db.add(revenue_event)
            db.commit()
        except Exception:
            pass
        raise e
