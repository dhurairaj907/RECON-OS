"""
RECON OS — Phase 9: Payment Reconciliation Schemas

Provider-neutral payment lifecycle, distinct from RecoveryCase/RecoveryAction
lifecycle (see services/reconciliation.py for the state machine). Read-only —
nothing here is ever written by a frontend, an AI model, or the Action
Engine; the only writer is services/reconciliation.py, driven exclusively by
authoritative provider events.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PaymentLifecycleStatus(str, Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"
    MISMATCHED = "MISMATCHED"


class ReconciliationStatus(str, Enum):
    IN_SYNC = "IN_SYNC"
    MISMATCH = "MISMATCH"
    UNVERIFIED = "UNVERIFIED"


class DisputeStatus(str, Enum):
    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------
class ReconciliationTimelineEntry(BaseModel):
    """One correlated event — either a RevenueEvent or an AuditLog row,
    merged and time-sorted so the timeline reads as a single narrative."""
    source: str                     # "event" | "audit"
    timestamp: datetime
    event_type: Optional[str] = None      # RevenueEvent.event_type
    processing_status: Optional[str] = None
    action: Optional[str] = None          # AuditLog.action
    detail: Optional[str] = None          # AuditLog.detail
    metadata: Optional[Dict[str, Any]] = None


class PaymentReconciliationResponse(BaseModel):
    payment_id: str
    razorpay_payment_id: str
    provider: str = "razorpay"

    raw_status: str                                # Payment.status (unchanged, existing field)
    lifecycle_status: Optional[PaymentLifecycleStatus] = None
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.UNVERIFIED

    amount: Decimal
    amount_paise: int
    refunded_amount_paise: int = 0
    remaining_captured_amount_paise: int

    dispute_status: Optional[DisputeStatus] = None

    timeline: List[ReconciliationTimelineEntry] = []


class ReconciliationMismatchItem(BaseModel):
    id: str
    action: str                     # RECONCILIATION_MISMATCH | PAYMENT_STATE_RECONCILIATION_MISMATCH
    detail: str
    payment_id: Optional[str] = None
    recovery_case_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class ReconciliationMismatchListResponse(BaseModel):
    items: List[ReconciliationMismatchItem] = []
    total: int = 0
    page: int = 1
    limit: int = 20
