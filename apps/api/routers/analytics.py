"""
RECON OS — Analytics Router  (Phase 4: PROVE)

    GET /api/v1/analytics    revenue recovery + operational metrics

Read-only, computed live from persisted RecoveryCase/RecoveryAction/
CaseIntelligence rows — see services/analytics_service.py. No new tracking
tables, no fabricated numbers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import AuthContext, get_auth_context
from database import get_db, get_org_merchant
from schemas.analytics import AnalyticsMetrics
from services.analytics_service import compute_analytics

router = APIRouter(tags=["Analytics"])


@router.get("/analytics", response_model=AnalyticsMetrics)
def get_analytics(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    merchant = get_org_merchant(db, ctx.organization)
    return compute_analytics(db, merchant.id)
