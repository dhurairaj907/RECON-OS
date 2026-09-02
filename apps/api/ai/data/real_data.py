"""
RECON OS — Phase 6: Real Data Extraction

Pulls genuinely-labeled rows from the EXISTING `recon_dev.db` — never a
second database, never synthetic values mixed in. A case only becomes a
labeled training row once it has both a diagnosed `failure_category`
(CaseIntelligence) and a SETTLED, NON-SIMULATED action outcome (RECOVERED/
FAILED/PARTIAL/EXPIRED/CANCELLED — never PENDING or UNKNOWN, which aren't
resolved yet and would be a leakage/mislabeling risk).

`RecoveryAction.simulated=True` rows (produced by the Simulator/evaluation
test lane — see services/simulator_service.py, evaluation/harness.py) are
EXCLUDED here, using the exact same flag `services/analytics_service.py`
already uses to keep simulated revenue out of `revenue_recovered`. Without
this filter, running the Simulator or the evaluation/demo scenarios against
this same dev database would silently leak test-lane outcomes into what
`ai/training/train.py` reports as "real" evidence — a genuine bug found and
fixed in the finalization audit, not a hypothetical concern.

As of Phase 6, `recon_dev.db` has ~38 recovery cases total — this function
will typically return a small double-digit-or-fewer row count, honestly
reported by ai/training/train.py as insufficient for standalone training
(see ai/data/synthetic.py for the dataset actually used to train).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from ai.data import DATASET_TYPE_REAL
from models.case_intelligence import CaseIntelligence
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from services.intelligence.context_builder import build_case_context

_SETTLED_OUTCOMES = {"RECOVERED", "FAILED", "PARTIAL", "EXPIRED", "CANCELLED"}


def extract_real_case_dataset(db: Session, merchant_id: Optional[object] = None) -> pd.DataFrame:
    q = db.query(RecoveryCase)
    if merchant_id is not None:
        q = q.filter(RecoveryCase.merchant_id == merchant_id)
    cases = q.all()

    rows = []
    for case in cases:
        action = (
            db.query(RecoveryAction)
            .filter(RecoveryAction.recovery_case_id == case.id)
            .order_by(RecoveryAction.created_at.desc())
            .first()
        )
        if action is None or (action.outcome or "").upper() not in _SETTLED_OUTCOMES:
            continue   # no settled outcome yet — not a usable label
        if action.simulated:
            continue   # Simulator/evaluation test-lane data — never counted as real evidence

        latest_intel = (
            db.query(CaseIntelligence)
            .filter(CaseIntelligence.recovery_case_id == case.id)
            .order_by(CaseIntelligence.version.desc())
            .first()
        )
        if latest_intel is None or not latest_intel.failure_category:
            continue   # never diagnosed — can't supply the failure_category feature

        ctx = build_case_context(db, case)
        d = ctx.model_dump(mode="json")

        recovered = (action.outcome or "").upper() == "RECOVERED"
        recovery_hours = None
        if recovered and action.completed_at and action.requested_at:
            recovery_hours = (action.completed_at - action.requested_at).total_seconds() / 3600.0

        d.update({
            "failure_category": latest_intel.failure_category,
            "recovered": recovered,
            "recovery_hours": recovery_hours,
            "is_anomaly_injected": False,   # unknown for real data — never claimed
            "dataset_type": DATASET_TYPE_REAL,
        })
        rows.append(d)

    return pd.DataFrame(rows)
