"""
RECON OS — Recovery Cases Router

List and view recovery cases created from payment failure events.
Phase 2: attaches a compact `intelligence` summary when an analysis exists.
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from database import get_db, seed_default_merchant
from models.recovery_case import RecoveryCase
from models.case_intelligence import CaseIntelligence
from schemas.recovery_case import RecoveryCaseResponse, RecoveryCaseListResponse
from schemas.intelligence import IntelligenceSummary

router = APIRouter(prefix="/recovery-cases", tags=["Recovery Cases"])


def _latest_intelligence_map(db: Session, case_ids: list) -> dict:
    """Return {recovery_case_id: CaseIntelligence} for the highest version per case."""
    if not case_ids:
        return {}
    rows = (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id.in_(case_ids))
        .order_by(CaseIntelligence.recovery_case_id, desc(CaseIntelligence.version))
        .all()
    )
    latest: dict = {}
    for r in rows:
        if r.recovery_case_id not in latest:
            latest[r.recovery_case_id] = r
    return latest


def _summary(ci: CaseIntelligence | None) -> Optional[IntelligenceSummary]:
    if ci is None:
        return None
    return IntelligenceSummary(
        status=ci.status,
        provider=ci.provider,
        version=str(ci.version),
        failure_category=ci.failure_category,
        recovery_probability=(
            float(ci.recovery_probability) if ci.recovery_probability is not None else None
        ),
        prediction_band=ci.prediction_band,
        recommended_action=ci.recommended_action,
        policy_verdict=ci.policy_verdict,
        requires_human=ci.requires_human,
        risk_level=ci.risk_level,
        analyzed_at=ci.created_at,
    )


@router.get("", response_model=RecoveryCaseListResponse)
def list_recovery_cases(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by case status (DETECTED, OPEN, RESOLVED, CLOSED)"),
    priority: Optional[str] = Query(None, description="Filter by priority (LOW, MEDIUM, HIGH, CRITICAL)"),
    search: Optional[str] = Query(None, description="Search by case number or failure reason"),
    db: Session = Depends(get_db),
):
    """
    Returns a paginated list of recovery cases with associated customer and payment data.
    """
    merchant = seed_default_merchant(db)
    query = db.query(RecoveryCase).options(
        joinedload(RecoveryCase.customer),
        joinedload(RecoveryCase.payment)
    ).filter(RecoveryCase.merchant_id == merchant.id)

    if status:
        query = query.filter(RecoveryCase.status == status)
    if priority:
        query = query.filter(RecoveryCase.priority == priority)
    if search:
        query = query.filter(
            (RecoveryCase.case_number.ilike(f"%{search}%")) |
            (RecoveryCase.failure_reason.ilike(f"%{search}%"))
        )

    total = query.count()
    items = query.order_by(desc(RecoveryCase.opened_at)).offset((page - 1) * limit).limit(limit).all()

    intel_map = _latest_intelligence_map(db, [item.id for item in items])
    responses = []
    for item in items:
        resp = RecoveryCaseResponse.model_validate(item)
        resp.intelligence = _summary(intel_map.get(item.id))
        responses.append(resp)

    return RecoveryCaseListResponse(
        items=responses,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{case_id}", response_model=RecoveryCaseResponse)
def get_recovery_case(case_id: str, db: Session = Depends(get_db)):
    """
    Get a single recovery case by internal UUID or Case Number (e.g. RC-10001).
    """
    merchant = seed_default_merchant(db)
    query = db.query(RecoveryCase).options(
        joinedload(RecoveryCase.customer),
        joinedload(RecoveryCase.payment)
    ).filter(RecoveryCase.merchant_id == merchant.id)

    try:
        uuid_val = UUID(case_id)
        case = query.filter((RecoveryCase.id == uuid_val) | (RecoveryCase.case_number == case_id)).first()
    except ValueError:
        case = query.filter(RecoveryCase.case_number == case_id).first()

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery case not found"
        )

    resp = RecoveryCaseResponse.model_validate(case)
    intel_map = _latest_intelligence_map(db, [case.id])
    resp.intelligence = _summary(intel_map.get(case.id))
    return resp
