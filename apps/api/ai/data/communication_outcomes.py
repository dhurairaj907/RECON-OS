"""
RECON OS — Phase 7: Communication Outcome Dataset  (training-data feedback)

Joins Communication + RecoveryAction + RecoveryCase into ONE clean row per
attempted communication, so a future phase (Phase 8) can train a model
without re-deriving this join from scratch. This module does NOT train
anything and is never called during Phase 7 request handling — it exists
purely so the outcome data is clean and usable later, per the phase
directive ("make the outcome data clean and usable... do not train models in
this phase").

Every row is REAL data (whatever exists in recon_dev.db) — there is no
synthetic variant of this dataset, since it only makes sense over genuine
attempted communications and their real, later-observed outcomes.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from models.communication import Communication
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase

_RESPONSE_OBSERVABLE_STATUSES = ("SENT", "DELIVERED")


def extract_communication_outcome_dataset(db: Session, merchant_id: Optional[object] = None) -> pd.DataFrame:
    """
    One row per Communication attempt with:
      - strategy chosen        (RecoveryAction.strategy_action, if any)
      - channel chosen         (Communication.channel)
      - message sent           (status in SENT/DELIVERED/FAILED/...)
      - message delivered      (status == DELIVERED)
      - customer response      NOT YET OBSERVABLE in this phase (RECON has no
                                inbound reply/click tracking) — always None,
                                explicitly, rather than guessed from a proxy.
      - payment recovered      (RecoveryAction.outcome == "RECOVERED", and
                                only counted if recovery happened AT OR AFTER
                                this message was sent — never attributed to a
                                message sent after the fact)
      - recovery amount        (RecoveryAction.recovered_amount)
      - time to recovery       (hours between this message's sent_at and the
                                action's completed_at, when both exist)
    """
    q = db.query(Communication)
    if merchant_id is not None:
        q = q.filter(Communication.merchant_id == merchant_id)
    comms = q.all()

    action_ids = {c.recovery_action_id for c in comms if c.recovery_action_id is not None}
    actions = {
        a.id: a for a in db.query(RecoveryAction).filter(RecoveryAction.id.in_(action_ids)).all()
    } if action_ids else {}
    case_ids = {c.recovery_case_id for c in comms}
    cases = {
        c.id: c for c in db.query(RecoveryCase).filter(RecoveryCase.id.in_(case_ids)).all()
    } if case_ids else {}

    rows = []
    for comm in comms:
        action = actions.get(comm.recovery_action_id) if comm.recovery_action_id else None
        case = cases.get(comm.recovery_case_id)

        message_sent = comm.status in _RESPONSE_OBSERVABLE_STATUSES
        message_delivered = comm.status == "DELIVERED"

        payment_recovered = False
        recovery_amount = 0.0
        time_to_recovery_hours = None
        if action is not None and (action.outcome or "").upper() == "RECOVERED" and action.completed_at:
            if comm.sent_at is None or comm.sent_at <= action.completed_at:
                payment_recovered = True
                recovery_amount = float(action.recovered_amount or 0)
                if comm.sent_at is not None:
                    time_to_recovery_hours = (action.completed_at - comm.sent_at).total_seconds() / 3600.0

        rows.append({
            "communication_id": str(comm.id),
            "recovery_case_id": str(comm.recovery_case_id),
            "recovery_action_id": str(comm.recovery_action_id) if comm.recovery_action_id else None,
            "strategy_chosen": action.strategy_action if action else None,
            "channel_chosen": comm.channel,
            "message_type": comm.message_type,
            "message_status": comm.status,
            "message_sent": message_sent,
            "message_delivered": message_delivered,
            "customer_response_observed": None,   # not tracked in this phase — never guessed
            "payment_recovered": payment_recovered,
            "recovery_amount": recovery_amount,
            "time_to_recovery_hours": time_to_recovery_hours,
            "amount_at_risk": float(case.amount_at_risk) if case is not None else None,
            "sent_at": comm.sent_at.isoformat() if comm.sent_at else None,
            "created_at": comm.created_at.isoformat() if comm.created_at else None,
        })

    return pd.DataFrame(rows)
