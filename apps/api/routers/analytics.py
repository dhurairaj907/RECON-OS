"""
RECON OS — Analytics Router  (Phase 4: PROVE)

    GET /api/v1/analytics    revenue recovery + operational metrics

Read-only, computed live from persisted RecoveryCase/RecoveryAction/
CaseIntelligence rows — see services/analytics_service.py. No new tracking
tables, no fabricated numbers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db, seed_default_merchant
from schemas.analytics import AnalyticsMetrics
from services.analytics_service import compute_analytics

router = APIRouter(tags=["Analytics"])


@router.get("/analytics", response_model=AnalyticsMetrics)
def get_analytics(db: Session = Depends(get_db)):
    merchant = seed_default_merchant(db)
    return compute_analytics(db, merchant.id)
