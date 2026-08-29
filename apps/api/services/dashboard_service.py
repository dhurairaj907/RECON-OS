"""
RECON OS — Dashboard Aggregation Service

Computes real-time Command Center metrics directly from PostgreSQL records.
Zero fabricated/hardcoded numbers.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List
from uuid import UUID

from sqlalchemy import func, case, desc
from sqlalchemy.orm import Session, joinedload

from models.customer import Customer
from models.payment import Payment
from models.revenue_event import RevenueEvent
from models.recovery_case import RecoveryCase
from models.case_intelligence import CaseIntelligence
from schemas.dashboard import DashboardMetrics, DailyTrendItem
from schemas.event import RevenueEventResponse
from schemas.recovery_case import RecoveryCaseResponse
from schemas.intelligence import IntelligenceMetrics


def get_dashboard_metrics(db: Session, merchant_id: UUID) -> DashboardMetrics:
    """
    Computes all Command Center KPI metrics directly from database state.
    """
    # 1. Revenue at risk (sum of active recovery cases)
    revenue_at_risk_query = db.query(
        func.coalesce(func.sum(RecoveryCase.amount_at_risk), Decimal("0.00"))
    ).filter(
        RecoveryCase.merchant_id == merchant_id,
        RecoveryCase.status.in_(["DETECTED", "OPEN"])
    )
    revenue_at_risk = revenue_at_risk_query.scalar() or Decimal("0.00")

    # 2. Revenue secured (sum of captured payments)
    revenue_secured_query = db.query(
        func.coalesce(func.sum(Payment.amount), Decimal("0.00"))
    ).filter(
        Payment.merchant_id == merchant_id,
        Payment.status == "captured"
    )
    revenue_secured = revenue_secured_query.scalar() or Decimal("0.00")

    # 3. Active recovery cases count
    active_recovery_cases = db.query(func.count(RecoveryCase.id)).filter(
        RecoveryCase.merchant_id == merchant_id,
        RecoveryCase.status.in_(["DETECTED", "OPEN"])
    ).scalar() or 0

    # 4. Payment counts by status
    payment_counts = db.query(
        Payment.status,
        func.count(Payment.id)
    ).filter(
        Payment.merchant_id == merchant_id
    ).group_by(Payment.status).all()

    status_map = {row[0]: row[1] for row in payment_counts}
    payment_failures = status_map.get("failed", 0)
    successful_payments = status_map.get("captured", 0)

    # 5. Events processed count
    events_processed = db.query(func.count(RevenueEvent.id)).filter(
        RevenueEvent.merchant_id == merchant_id,
        RevenueEvent.processing_status == "processed"
    ).scalar() or 0

    # 6. Total customers count
    total_customers = db.query(func.count(Customer.id)).filter(
        Customer.merchant_id == merchant_id
    ).scalar() or 0

    # 7. Recent events (top 10)
    recent_events_orm = db.query(RevenueEvent).filter(
        RevenueEvent.merchant_id == merchant_id
    ).order_by(desc(RevenueEvent.received_at)).limit(10).all()
    recent_events = [RevenueEventResponse.model_validate(e) for e in recent_events_orm]

    # 8. Recent recovery cases (top 10)
    recent_cases_orm = db.query(RecoveryCase).options(
        joinedload(RecoveryCase.customer),
        joinedload(RecoveryCase.payment)
    ).filter(
        RecoveryCase.merchant_id == merchant_id
    ).order_by(desc(RecoveryCase.opened_at)).limit(10).all()
    recent_cases = [RecoveryCaseResponse.model_validate(c) for c in recent_cases_orm]

    # 9. Daily trends (past 7 days)
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    payments_7d = db.query(
        func.date(Payment.created_at).label("day"),
        Payment.status,
        func.sum(Payment.amount).label("total_amount"),
        func.count(Payment.id).label("total_count")
    ).filter(
        Payment.merchant_id == merchant_id,
        Payment.created_at >= seven_days_ago
    ).group_by(
        func.date(Payment.created_at),
        Payment.status
    ).all()

    daily_data = {}
    for i in range(7):
        day_str = (seven_days_ago + timedelta(days=i+1)).strftime("%Y-%m-%d")
        daily_data[day_str] = {
            "failed_amount": Decimal("0.00"),
            "captured_amount": Decimal("0.00"),
            "failed_count": 0,
            "captured_count": 0,
        }

    for row in payments_7d:
        day_str = str(row.day)
        if day_str in daily_data:
            if row.status == "failed":
                daily_data[day_str]["failed_amount"] = row.total_amount or Decimal("0.00")
                daily_data[day_str]["failed_count"] = row.total_count or 0
            elif row.status == "captured":
                daily_data[day_str]["captured_amount"] = row.total_amount or Decimal("0.00")
                daily_data[day_str]["captured_count"] = row.total_count or 0

    daily_trends = [
        DailyTrendItem(
            date=day_str,
            failed_amount=val["failed_amount"],
            captured_amount=val["captured_amount"],
            failed_count=val["failed_count"],
            captured_count=val["captured_count"],
        )
        for day_str, val in sorted(daily_data.items())
    ]

    # 10. Phase 2 (THINK) — intelligence decision metrics (latest analysis per case)
    intel_rows = (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.merchant_id == merchant_id)
        .order_by(CaseIntelligence.recovery_case_id, desc(CaseIntelligence.version))
        .all()
    )
    latest_by_case = {}
    for row in intel_rows:
        if row.recovery_case_id not in latest_by_case:
            latest_by_case[row.recovery_case_id] = row

    intelligence_metrics = None
    if latest_by_case:
        latest = list(latest_by_case.values())
        intelligence_metrics = IntelligenceMetrics(
            cases_analyzed=len(latest),
            high_recovery_probability=sum(1 for r in latest if (r.prediction_band or "") == "HIGH"),
            needs_approval=sum(1 for r in latest if (r.policy_verdict or "") == "NEEDS_APPROVAL"),
            policy_rejected=sum(1 for r in latest if (r.policy_verdict or "") == "REJECTED"),
            policy_approved=sum(1 for r in latest if (r.policy_verdict or "") == "APPROVED"),
        )

    return DashboardMetrics(
        revenue_at_risk=revenue_at_risk,
        revenue_secured=revenue_secured,
        active_recovery_cases=active_recovery_cases,
        payment_failures=payment_failures,
        successful_payments=successful_payments,
        events_processed=events_processed,
        total_customers=total_customers,
        recent_events=recent_events,
        recent_cases=recent_cases,
        daily_trends=daily_trends,
        intelligence=intelligence_metrics,
    )
