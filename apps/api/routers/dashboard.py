"""
RECON OS — Dashboard Router

Provides metrics and aggregated statistics for the Command Center.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import AuthContext, get_auth_context
from database import get_db, get_org_merchant
from schemas.dashboard import DashboardMetrics
from services.dashboard_service import get_dashboard_metrics

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/metrics", response_model=DashboardMetrics)
def get_metrics(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    """
    Returns real-time aggregated metrics for the Command Center:
    - Revenue at Risk (sum of active cases)
    - Revenue Secured (sum of captured payments)
    - Active Recovery Cases count
    - Payment Failures & Successes
    - Recent Events & Recent Cases
    - 7-day volume trends
    """
    merchant = get_org_merchant(db, ctx.organization)
    return get_dashboard_metrics(db=db, merchant_id=merchant.id)
