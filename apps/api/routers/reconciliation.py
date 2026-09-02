"""
RECON OS — Phase 9: Payment Reconciliation Router

    GET /api/v1/payments/{payment_id}/reconciliation   lifecycle + timeline for one payment
    GET /api/v1/reconciliation/mismatches               org-wide mismatch list

Read-only — no endpoint here ever mutates a Payment, RecoveryCase, or
RecoveryAction. The only writer of payment lifecycle state is
services/reconciliation.py, driven exclusively by authoritative provider
events processed in services/event_processor.py.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import AuthContext, get_auth_context
from database import get_db, get_org_merchant
from models.audit_log import AuditLog
from models.payment import Payment
from models.revenue_event import RevenueEvent
from schemas.reconciliation import (
    PaymentReconciliationResponse,
    ReconciliationMismatchItem,
    ReconciliationMismatchListResponse,
    ReconciliationTimelineEntry,
)

router = APIRouter(tags=["Reconciliation"])

_MISMATCH_AUDIT_ACTIONS = ("RECONCILIATION_MISMATCH", "PAYMENT_STATE_RECONCILIATION_MISMATCH")


def _resolve_payment(db: Session, merchant_id, payment_id: str) -> Payment:
    q = db.query(Payment).filter(Payment.merchant_id == merchant_id)
    try:
        uid = UUID(payment_id)
        payment = q.filter((Payment.id == uid) | (Payment.razorpay_payment_id == payment_id)).first()
    except ValueError:
        payment = q.filter(Payment.razorpay_payment_id == payment_id).first()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment


@router.get("/payments/{payment_id}/reconciliation", response_model=PaymentReconciliationResponse)
def get_payment_reconciliation(
    payment_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    merchant = get_org_merchant(db, ctx.organization)
    payment = _resolve_payment(db, merchant.id, payment_id)

    events = (
        db.query(RevenueEvent)
        .filter(RevenueEvent.merchant_id == merchant.id,
                RevenueEvent.correlation_id == payment.razorpay_payment_id)
        .order_by(RevenueEvent.received_at)
        .all()
    )
    # Same substring-on-detail correlation approach routers/audit_logs.py
    # already uses for its `search` filter — every reconciliation audit
    # entry's detail includes the payment's own razorpay_payment_id.
    audits = (
        db.query(AuditLog)
        .filter(AuditLog.merchant_id == merchant.id,
                AuditLog.detail.ilike(f"%{payment.razorpay_payment_id}%"))
        .order_by(AuditLog.created_at)
        .all()
    )

    timeline = [
        ReconciliationTimelineEntry(
            source="event", timestamp=e.received_at, event_type=e.event_type,
            processing_status=e.processing_status,
        )
        for e in events
    ] + [
        ReconciliationTimelineEntry(
            source="audit", timestamp=a.created_at, action=a.action, detail=a.detail,
            metadata=a.metadata_json,
        )
        for a in audits
    ]
    timeline.sort(key=lambda t: t.timestamp)

    remaining = int(payment.amount_paise or 0) - int(payment.refunded_amount_paise or 0)

    return PaymentReconciliationResponse(
        payment_id=str(payment.id),
        razorpay_payment_id=payment.razorpay_payment_id,
        raw_status=payment.status,
        lifecycle_status=payment.lifecycle_status,
        reconciliation_status=payment.reconciliation_status or "UNVERIFIED",
        amount=payment.amount,
        amount_paise=payment.amount_paise,
        refunded_amount_paise=int(payment.refunded_amount_paise or 0),
        remaining_captured_amount_paise=max(remaining, 0),
        dispute_status=payment.dispute_status,
        timeline=timeline,
    )


@router.get("/reconciliation/mismatches", response_model=ReconciliationMismatchListResponse)
def list_reconciliation_mismatches(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    merchant = get_org_merchant(db, ctx.organization)
    q = db.query(AuditLog).filter(
        AuditLog.merchant_id == merchant.id,
        AuditLog.action.in_(_MISMATCH_AUDIT_ACTIONS),
    )
    total = q.count()
    rows = q.order_by(desc(AuditLog.created_at)).offset((page - 1) * limit).limit(limit).all()

    items = [
        ReconciliationMismatchItem(
            id=str(r.id),
            action=r.action,
            detail=r.detail,
            payment_id=(r.metadata_json or {}).get("identifier") if r.action == "RECONCILIATION_MISMATCH"
            else (r.metadata_json or {}).get("payment_id"),
            recovery_case_id=str(r.recovery_case_id) if r.recovery_case_id else None,
            metadata=r.metadata_json,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return ReconciliationMismatchListResponse(items=items, total=total, page=page, limit=limit)
