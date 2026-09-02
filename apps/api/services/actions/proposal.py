"""
RECON OS — Phase 3: Action Proposal

Turns the latest deterministic strategy/policy result for a recovery case into an
explicit `ActionProposal`. A proposal is NOT execution — it is an instruction for
the Action Executor to validate.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from config import settings
from integrations.razorpay.adapter import get_razorpay_adapter
from models.case_intelligence import CaseIntelligence
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from schemas.action import ActionProposal, ActionType
from services.actions.common import (
    PAYMENT_LINK_ELIGIBLE_STRATEGIES,
    TERMINAL_CASE_STATUSES,
    audit_action,
    idempotency_key_for,
    reference_id_for,
    to_paise,
)

logger = logging.getLogger("recon.services.actions.proposal")


def _latest_intelligence(db: Session, case_id) -> CaseIntelligence | None:
    return (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id == case_id)
        .order_by(CaseIntelligence.version.desc())
        .first()
    )


def build_proposal(db: Session, case: RecoveryCase) -> ActionProposal:
    adapter = get_razorpay_adapter()
    amount = Decimal(case.amount_at_risk or 0)
    base = dict(
        recovery_case_id=str(case.id),
        case_number=case.case_number,
        currency=case.currency or "INR",
        amount=amount,
        test_mode=bool(adapter.test_mode),
        razorpay_configured=adapter.is_configured(),
        simulator_enabled=bool(settings.RECON_SIMULATOR_ENABLED),
        automatic_execution_enabled=bool(settings.AUTOMATIC_ACTION_EXECUTION_ENABLED),
    )

    ci = _latest_intelligence(db, case.id)
    if ci is None or ci.status == "FAILED":
        return ActionProposal(
            proposable=False, reason="Recovery case has not been analysed yet — run intelligence first.",
            not_proposable_reason="NOT_ANALYZED", **base,
        )

    strategy_action = ci.recommended_action or ""
    policy_verdict = ci.policy_verdict or ""

    if (case.status or "").upper() in TERMINAL_CASE_STATUSES:
        return ActionProposal(
            proposable=False, strategy_action=strategy_action, policy_verdict=policy_verdict,
            reason=f"Recovery case is {case.status} — no action needed.",
            not_proposable_reason="CASE_NOT_ELIGIBLE", **base,
        )

    if strategy_action not in PAYMENT_LINK_ELIGIBLE_STRATEGIES:
        return ActionProposal(
            proposable=False, strategy_action=strategy_action, policy_verdict=policy_verdict,
            reason=(f"Strategy '{strategy_action or 'NONE'}' has no executable Phase 3 action. "
                    "Phase 3 implements CREATE_PAYMENT_LINK only "
                    "(for RETRY_NOW / RETRY_DELAYED / SEND_PAYMENT_LINK intents)."),
            not_proposable_reason="STRATEGY_NOT_ELIGIBLE", **base,
        )

    return ActionProposal(
        proposable=True,
        action_type=ActionType.CREATE_PAYMENT_LINK,
        reference_id=reference_id_for(case.case_number),
        strategy_action=strategy_action,
        policy_verdict=policy_verdict,
        reason=(
            "Strategy recommends recovering this payment. A failed Razorpay payment "
            "cannot be re-charged via API, so the executable recovery action is a "
            "Razorpay TEST MODE Payment Link the customer can pay on. Execution "
            "re-checks the Policy Engine server-side before any Razorpay call."
        ),
        **base,
    )


def get_or_create_action(db: Session, case: RecoveryCase) -> tuple[RecoveryAction | None, ActionProposal]:
    """
    Idempotent: at most one CREATE_PAYMENT_LINK action per recovery case.
    Returns (action_or_None, proposal). Only creates a row when the proposal is
    proposable and one does not already exist.
    """
    proposal = build_proposal(db, case)

    existing = (
        db.query(RecoveryAction)
        .filter(
            RecoveryAction.recovery_case_id == case.id,
            RecoveryAction.action_type == ActionType.CREATE_PAYMENT_LINK.value,
        )
        .order_by(RecoveryAction.action_version.desc())
        .first()
    )
    if existing is not None:
        return existing, proposal

    if not proposal.proposable:
        return None, proposal

    version = 1
    amount = Decimal(case.amount_at_risk or 0)
    action = RecoveryAction(
        recovery_case_id=case.id,
        merchant_id=case.merchant_id,
        action_type=ActionType.CREATE_PAYMENT_LINK.value,
        action_version=version,
        status="PROPOSED",
        outcome="PENDING",
        idempotency_key=idempotency_key_for(case.id, ActionType.CREATE_PAYMENT_LINK.value, version),
        reference_id=reference_id_for(case.case_number, version),
        strategy_action=proposal.strategy_action,
        policy_verdict=proposal.policy_verdict,
        amount=amount,
        amount_paise=to_paise(amount),
        currency=case.currency or "INR",
        provider="RAZORPAY",
    )
    db.add(action)
    db.flush()
    audit_action(
        db, action, "ACTION_ENGINE", "ACTION_PROPOSED",
        f"Proposed {action.action_type} for {case.case_number} "
        f"(strategy={proposal.strategy_action}, policy@analysis={proposal.policy_verdict})",
        {"amount": str(amount), "currency": action.currency,
         "strategy_action": proposal.strategy_action,
         "policy_verdict_at_analysis": proposal.policy_verdict},
    )
    db.commit()
    db.refresh(action)
    return action, proposal
