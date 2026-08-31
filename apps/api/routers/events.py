"""
RECON OS — Events Router

List and view revenue events.
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from auth import AuthContext, get_auth_context
from database import get_db, get_org_merchant
from models.revenue_event import RevenueEvent
from schemas.event import RevenueEventResponse, RevenueEventListResponse

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=RevenueEventListResponse)
def list_events(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    status: Optional[str] = Query(None, description="Filter by processing status"),
    search: Optional[str] = Query(None, description="Search by event ID"),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Returns a paginated list of revenue events with optional filtering.
    """
    merchant = get_org_merchant(db, ctx.organization)
    query = db.query(RevenueEvent).filter(RevenueEvent.merchant_id == merchant.id)

    if event_type:
        query = query.filter(RevenueEvent.event_type == event_type)
    if status:
        query = query.filter(RevenueEvent.processing_status == status)
    if search:
        query = query.filter(RevenueEvent.razorpay_event_id.ilike(f"%{search}%"))

    total = query.count()
    items = query.order_by(desc(RevenueEvent.received_at)).offset((page - 1) * limit).limit(limit).all()

    return RevenueEventListResponse(
        items=[RevenueEventResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{event_id}", response_model=RevenueEventResponse)
def get_event(event_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    """
    Get a single revenue event by internal UUID or Razorpay event ID.
    """
    merchant = get_org_merchant(db, ctx.organization)
    query = db.query(RevenueEvent).filter(RevenueEvent.merchant_id == merchant.id)

    # Try matching UUID or razorpay_event_id
    try:
        uuid_val = UUID(event_id)
        event = query.filter((RevenueEvent.id == uuid_val) | (RevenueEvent.razorpay_event_id == event_id)).first()
    except ValueError:
        event = query.filter(RevenueEvent.razorpay_event_id == event_id).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Revenue event not found"
        )

    return RevenueEventResponse.model_validate(event)
