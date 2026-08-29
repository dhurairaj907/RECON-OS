"""
RECON OS — Audit Logs Router

Query the immutable system audit trail.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db, seed_default_merchant
from models.audit_log import AuditLog
from schemas.audit_log import AuditLogResponse, AuditLogListResponse

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    action: Optional[str] = Query(None, description="Filter by action"),
    actor: Optional[str] = Query(None, description="Filter by actor"),
    search: Optional[str] = Query(None, description="Search in detail text"),
    db: Session = Depends(get_db),
):
    """
    Returns a paginated list of audit records for full operational transparency.
    """
    merchant = seed_default_merchant(db)
    query = db.query(AuditLog).filter(AuditLog.merchant_id == merchant.id)

    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if search:
        query = query.filter(AuditLog.detail.ilike(f"%{search}%"))

    total = query.count()
    items = query.order_by(desc(AuditLog.created_at)).offset((page - 1) * limit).limit(limit).all()

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        limit=limit,
    )
