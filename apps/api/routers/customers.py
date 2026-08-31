"""
RECON OS — Customers Router

List and view customer profiles with payment aggregate information.
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from auth import AuthContext, get_auth_context
from database import get_db, get_org_merchant
from models.customer import Customer
from schemas.customer import CustomerResponse, CustomerListResponse

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("", response_model=CustomerListResponse)
def list_customers(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Returns a paginated list of customers with aggregates.
    """
    merchant = get_org_merchant(db, ctx.organization)
    query = db.query(Customer).filter(Customer.merchant_id == merchant.id)

    if search:
        query = query.filter(
            (Customer.name.ilike(f"%{search}%")) |
            (Customer.email.ilike(f"%{search}%")) |
            (Customer.phone.ilike(f"%{search}%"))
        )

    total = query.count()
    items = query.order_by(
        Customer.last_payment_at.desc().nulls_last(),
        Customer.created_at.desc()
    ).offset((page - 1) * limit).limit(limit).all()

    return CustomerListResponse(
        items=[CustomerResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    """
    Get a customer profile by UUID or Razorpay customer ID.
    """
    merchant = get_org_merchant(db, ctx.organization)
    query = db.query(Customer).filter(Customer.merchant_id == merchant.id)

    try:
        uuid_val = UUID(customer_id)
        customer = query.filter((Customer.id == uuid_val) | (Customer.razorpay_customer_id == customer_id)).first()
    except ValueError:
        customer = query.filter(Customer.razorpay_customer_id == customer_id).first()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    return CustomerResponse.model_validate(customer)
