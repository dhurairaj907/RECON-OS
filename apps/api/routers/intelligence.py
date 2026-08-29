"""
RECON OS — Intelligence Router  (Phase 2: THINK)

    GET  /api/v1/recovery-cases/{case_id}/intelligence           latest result
    POST /api/v1/recovery-cases/{case_id}/intelligence:analyze    run (safe to repeat)
    GET  /api/v1/intelligence                                     analysed-case list

No financial actions. No secrets in responses.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from config import settings
from database import get_db, seed_default_merchant
from models.case_intelligence import CaseIntelligence
from models.recovery_case import RecoveryCase
from schemas.intelligence import (
    IntelligenceEnvelope,
    IntelligenceListItem,
    IntelligenceListResponse,
)
from services.intelligence.orchestrator import run_intelligence

logger = logging.getLogger("recon.routers.intelligence")

router = APIRouter(tags=["Intelligence"])


def _resolve_case(db: Session, merchant_id, case_id: str) -> RecoveryCase:
    query = db.query(RecoveryCase).options(
        joinedload(RecoveryCase.customer)
    ).filter(RecoveryCase.merchant_id == merchant_id)
    try:
        uuid_val = UUID(case_id)
        case = query.filter(
            (RecoveryCase.id == uuid_val) | (RecoveryCase.case_number == case_id)
        ).first()
    except ValueError:
        case = query.filter(RecoveryCase.case_number == case_id).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recovery case not found"
        )
    return case


def _latest_intel(db: Session, case_id) -> CaseIntelligence | None:
    return (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id == case_id)
        .order_by(CaseIntelligence.version.desc())
        .first()
    )


def _envelope(case: RecoveryCase, ci: CaseIntelligence | None) -> IntelligenceEnvelope:
    if ci is None:
        return IntelligenceEnvelope(
            case_id=str(case.id),
            case_number=case.case_number,
            analyzed=False,
            intelligence_enabled=settings.INTELLIGENCE_ENABLED,
            status="NOT_RUN",
        )
    return IntelligenceEnvelope(
        case_id=str(case.id),
        case_number=case.case_number,
        analyzed=ci.status != "FAILED",
        intelligence_enabled=settings.INTELLIGENCE_ENABLED,
        status=ci.status,
        provider=ci.provider,
        version=str(ci.version),
        analyzed_at=ci.created_at,
        diagnosis=ci.diagnosis_json,
        prediction=ci.prediction_json,
        strategy=ci.strategy_json,
        policy=ci.policy_json,
        context=ci.context_json,
        error_message=ci.error_message,
    )


@router.get(
    "/recovery-cases/{case_id}/intelligence",
    response_model=IntelligenceEnvelope,
)
def get_case_intelligence(case_id: str, db: Session = Depends(get_db)):
    """Return the latest intelligence result for a recovery case."""
    merchant = seed_default_merchant(db)
    case = _resolve_case(db, merchant.id, case_id)
    return _envelope(case, _latest_intel(db, case.id))


@router.post(
    "/recovery-cases/{case_id}/intelligence:analyze",
    response_model=IntelligenceEnvelope,
    status_code=status.HTTP_200_OK,
)
def analyze_case_intelligence(case_id: str, db: Session = Depends(get_db)):
    """
    Manually run the deterministic intelligence pipeline for a recovery case.

    Safe to repeat: each call persists a new version; it never creates or
    duplicates a recovery case. Works even when INTELLIGENCE_ENABLED is False.
    """
    merchant = seed_default_merchant(db)
    case = _resolve_case(db, merchant.id, case_id)
    ci = run_intelligence(db, case.id, trigger="manual")
    # run_intelligence owns its transaction; re-resolve the row for a clean read
    fresh = _latest_intel(db, case.id) or ci
    return _envelope(case, fresh)


@router.get("/intelligence", response_model=IntelligenceListResponse)
def list_intelligence(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    verdict: str | None = Query(None, description="Filter by policy verdict"),
    band: str | None = Query(None, description="Filter by prediction band"),
    db: Session = Depends(get_db),
):
    """List recovery cases that have been analysed (latest analysis per case)."""
    merchant = seed_default_merchant(db)

    rows = (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.merchant_id == merchant.id)
        .order_by(CaseIntelligence.recovery_case_id, desc(CaseIntelligence.version))
        .all()
    )
    latest: dict = {}
    for r in rows:
        if r.recovery_case_id not in latest:
            latest[r.recovery_case_id] = r

    cases = {
        c.id: c
        for c in db.query(RecoveryCase)
        .options(joinedload(RecoveryCase.customer))
        .filter(RecoveryCase.id.in_(list(latest.keys())))
        .all()
    } if latest else {}

    items: list[IntelligenceListItem] = []
    for case_id, ci in latest.items():
        case = cases.get(case_id)
        if case is None:
            continue
        if verdict and (ci.policy_verdict or "") != verdict:
            continue
        if band and (ci.prediction_band or "") != band:
            continue
        items.append(IntelligenceListItem(
            case_id=str(case.id),
            case_number=case.case_number,
            customer_name=(case.customer.name if case.customer else None),
            amount_at_risk=case.amount_at_risk,
            currency=case.currency or "INR",
            failure_category=ci.failure_category,
            recovery_probability=(
                float(ci.recovery_probability) if ci.recovery_probability is not None else None
            ),
            prediction_band=ci.prediction_band,
            recommended_action=ci.recommended_action,
            policy_verdict=ci.policy_verdict,
            risk_level=ci.risk_level,
            status=ci.status,
            provider=ci.provider,
            version=str(ci.version),
            analyzed_at=ci.created_at,
        ))

    _epoch = datetime.min.replace(tzinfo=timezone.utc)
    items.sort(key=lambda i: i.analyzed_at or _epoch, reverse=True)
    total = len(items)
    start = (page - 1) * limit
    return IntelligenceListResponse(
        items=items[start:start + limit], total=total, page=page, limit=limit
    )
