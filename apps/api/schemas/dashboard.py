"""
RECON OS — Dashboard Schemas

Pydantic schemas for Command Center aggregated metrics and trends.
"""

from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from schemas.event import RevenueEventResponse
from schemas.recovery_case import RecoveryCaseResponse
from schemas.intelligence import IntelligenceMetrics


class DailyTrendItem(BaseModel):
    date: str
    failed_amount: Decimal
    captured_amount: Decimal
    failed_count: int
    captured_count: int


class DashboardMetrics(BaseModel):
    revenue_at_risk: Decimal
    revenue_secured: Decimal
    active_recovery_cases: int
    payment_failures: int
    successful_payments: int
    events_processed: int
    total_customers: int
    recent_events: List[RevenueEventResponse] = []
    recent_cases: List[RecoveryCaseResponse] = []
    daily_trends: List[DailyTrendItem] = []
    # Phase 2 (THINK): None until at least one case has been analysed.
    intelligence: Optional[IntelligenceMetrics] = None
