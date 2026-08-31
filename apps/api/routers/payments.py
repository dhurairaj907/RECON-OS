"""
RECON OS — Payments Router

List and view payment records.
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from auth import AuthContext, get_auth_context
from database import get_db, get_org_merchant
from models.payment import Payment
from schemas.payment import PaymentResponse, PaymentListResponse

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get("", response_model=PaymentListResponse)
def list_payments(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by payment status"),
    method: Optional[str] = Query(None, description="Filter by payment method"),
    search: Optional[str] = Query(None, description="Search by payment ID or order ID"),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Returns a paginated list of payments with optional status/method filtering.
    """
    merchant = get_org_merchant(db, ctx.organization)
    query = db.query(Payment).filter(Payment.merchant_id == merchant.id)

    if status_filter:
        query = query.filter(Payment.status == status_filter)
    if method:
        query = query.filter(Payment.method == method)
    if search:
        query = query.filter(
            (Payment.razorpay_payment_id.ilike(f"%{search}%")) |
            (Payment.razorpay_order_id.ilike(f"%{search}%"))
        )

    total = query.count()
    items = query.order_by(desc(Payment.created_at)).offset((page - 1) * limit).limit(limit).all()

    return PaymentListResponse(
        items=[PaymentResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    """
    Get a single payment record by internal UUID or Razorpay payment ID.
    """
    merchant = get_org_merchant(db, ctx.organization)
    query = db.query(Payment).filter(Payment.merchant_id == merchant.id)

    try:
        uuid_val = UUID(payment_id)
        payment = query.filter((Payment.id == uuid_val) | (Payment.razorpay_payment_id == payment_id)).first()
    except ValueError:
        payment = query.filter(Payment.razorpay_payment_id == payment_id).first()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )

    return PaymentResponse.model_validate(payment)
