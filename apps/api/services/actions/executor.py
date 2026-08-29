"""
RECON OS — Phase 3: Action Executor  (SAFETY-CRITICAL)

execute_action(db, action_id):
    load action
      -> idempotency: already executed? return existing (NO second Razorpay call)
      -> load recovery case
      -> rebuild CaseContext  (server-side, fresh)
      -> re-run diagnosis / prediction / strategy
      -> RE-EVALUATE the deterministic Policy Engine  (canonical SEND_PAYMENT_LINK gate)
      -> verify verdict == APPROVED   (NEEDS_APPROVAL / REJECTED -> BLOCKED, no execution)
      -> validate amount / currency
      -> verify Razorpay configured + TEST MODE + test key
      -> idempotency re-check
      -> call Razorpay adapter (POST /v1/payment_links)
      -> persist normalised result  (status EXECUTED, outcome PENDING — NOT recovered)
      -> write full audit trail
      -> return RecoveryAction

Never trusts a stored verdict, a frontend value, or an AI value. Everything is
re-derived here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from integrations.razorpay.adapter import get_razorpay_adapter
from models.recovery_action import RecoveryAction
from models.recovery_case import RecoveryCase
from schemas.intelligence import StrategyAction, StrategyResult
from services.actions.common import (
    PAYMENT_LINK_ELIGIBLE_STRATEGIES,
    TERMINAL_CASE_STATUSES,
    audit_action,
    to_paise,
    ui_state,
)
from services.intelligence.ai_diagnosis import diagnose_case
from services.intelligence.context_builder import build_case_context
from services.intelligence.policy_engine import evaluate_policy
from services.intelligence.prediction import predict
from services.intelligence.strategy import recommend_strategy

logger = logging.getLogger("recon.services.actions.executor")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_payment_link_strategy(confidence: float) -> StrategyResult:
    """
    The Policy Engine is re-run against the action we ACTUALLY take
    (SEND_PAYMENT_LINK) — not whatever the strategy layer nominally recommended —
    so the contact-limit and payment-link rules genuinely gate execution.
    """
    return StrategyResult(
        action=StrategyAction.SEND_PAYMENT_LINK,
        params={},
        rationale="Canonical payment-link policy gate for Phase 3 execution.",
        confidence=max(0.0, min(1.0, confidence)),
        alternatives=[],
        provider="DETERMINISTIC",
    )


def execute_action(db: Session, action_id) -> RecoveryAction:
    action = db.query(RecoveryAction).filter(RecoveryAction.id == action_id).first()
    if action is None:
        raise ValueError(f"Recovery action {action_id} not found")

    # --- IDEMPOTENCY: a Payment Link was already created — return it, no re-call ---
    if action.provider_action_id or action.status in ("EXECUTED", "EXECUTING"):
        logger.info("Action %s already executed (%s) — returning existing result",
                    action.reference_id, action.status)
        return action

    case = db.query(RecoveryCase).filter(RecoveryCase.id == action.recovery_case_id).first()
    if case is None:
        return _block(db, action, "CASE_NOT_ELIGIBLE", "Recovery case not found.")

    # Fresh attempt — clear any prior block/error so a retry after a fix is clean.
    action.blocked_reason = None
    action.error_code = None
    action.error_message = None

    audit_action(db, action, "ACTION_ENGINE", "ACTION_EXECUTION_STARTED",
                 f"Execution requested for {action.reference_id} ({case.case_number})")
    db.commit()

    # --- Re-derive everything server-side ---------------------------------
    ctx = build_case_context(db, case)
    diagnosis, _ = diagnose_case(ctx)
    prediction = predict(ctx, diagnosis)
    strategy = recommend_strategy(ctx, diagnosis, prediction)

    if (case.status or "").upper() in TERMINAL_CASE_STATUSES:
        return _block(db, action, "CASE_NOT_ELIGIBLE",
                      f"Recovery case is {case.status} — nothing to recover.")

    if strategy.action.value not in PAYMENT_LINK_ELIGIBLE_STRATEGIES:
        return _block(db, action, "STRATEGY_NOT_ELIGIBLE",
                      f"Fresh strategy is {strategy.action.value} — not a payment-link "
                      f"recovery intent.")

    # --- RE-EVALUATE POLICY (authoritative) ------------------------------
    policy = evaluate_policy(ctx, diagnosis, prediction,
                             _canonical_payment_link_strategy(strategy.confidence))
    action.strategy_action = strategy.action.value
    action.policy_verdict = policy.verdict.value
    action.policy_json = policy.model_dump(mode="json")
    audit_action(db, action, "POLICY_ENGINE", "ACTION_POLICY_CHECKED",
                 f"Re-evaluated policy for execution: {policy.verdict.value} "
                 f"(risk {policy.risk_level.value}) — {policy.reason}",
                 {"verdict": policy.verdict.value,
                  "risk_level": policy.risk_level.value,
                  "violated_rules": policy.violated_rules})
    db.commit()

    if policy.verdict.value == "NEEDS_APPROVAL":
        return _block(db, action, "NEEDS_APPROVAL", policy.reason)
    if policy.verdict.value == "REJECTED":
        return _block(db, action, "POLICY_REJECTED", policy.reason)

    # verdict == APPROVED
    action.status = "APPROVED"
    action.approved_at = _now()
    audit_action(db, action, "POLICY_ENGINE", "ACTION_APPROVED",
                 f"Policy APPROVED execution of {action.action_type} for {case.case_number}")
    db.commit()

    # --- Validate money -------------------------------------------------
    amount = Decimal(action.amount or 0)
    if amount <= 0:
        return _block(db, action, "INVALID_AMOUNT", f"Invalid amount {amount}.")
    currency = (action.currency or "INR").upper()
    if currency != "INR":
        return _block(db, action, "INVALID_CURRENCY",
                      f"Phase 3 supports INR only (got {currency}).")
    amount_paise = to_paise(amount)
    if amount_paise < 100:
        return _block(db, action, "INVALID_AMOUNT",
                      "Amount below Razorpay minimum (100 paise).")
    action.amount_paise = amount_paise

    # --- Verify Razorpay config + TEST MODE ----------------------------
    adapter = get_razorpay_adapter()
    if not adapter.is_configured():
        return _block(db, action, "RAZORPAY_NOT_CONFIGURED",
                      "Razorpay credentials are not configured.",
                      error_code="RAZORPAY_NOT_CONFIGURED")
    if not adapter.test_mode:
        return _block(db, action, "TEST_MODE_DISABLED",
                      "RAZORPAY_TEST_MODE is false — live execution is refused.",
                      error_code="RAZORPAY_TEST_MODE_DISABLED")
    if not adapter.is_test_key():
        return _block(db, action, "RAZORPAY_NOT_TEST_KEY",
                      "RAZORPAY_KEY_ID is not a test key (expected rzp_test_*).",
                      error_code="RAZORPAY_NOT_TEST_KEY")

    # --- IDEMPOTENCY re-check right before the call --------------------
    db.refresh(action)
    if action.provider_action_id:
        return action

    action.status = "EXECUTING"
    db.commit()

    cust = case.customer
    result = adapter.create_payment_link(
        amount_paise=amount_paise,
        currency="INR",
        reference_id=action.reference_id,
        description=f"RECON OS revenue recovery — {case.case_number}",
        customer_name=(cust.name if cust else None),
        customer_email=(cust.email if cust else None),
        customer_contact=(cust.phone if cust else None),
        notes={
            "recon_case": case.case_number,
            "recon_action_id": str(action.id),
            "recon_reference_id": action.reference_id,
        },
    )

    if not result.ok:
        action.status = "FAILED"
        action.error_code = result.error_code
        action.error_message = result.error_message
        audit_action(db, action, "RAZORPAY_ADAPTER", "ACTION_EXECUTION_FAILED",
                     f"Payment Link creation failed: {result.error_code} — {result.error_message}",
                     {"error_code": result.error_code})
        audit_action(db, action, "RECON_ENGINE", "RECOVERY_FAILED",
                     f"Recovery action failed for {case.case_number}")
        db.commit()
        db.refresh(action)
        return action

    # Success — Payment Link created. This is NOT revenue recovered.
    action.status = "EXECUTED"
    action.outcome = "PENDING"
    action.executed_at = _now()
    action.provider_action_id = result.payment_link_id
    action.provider_status = result.status or "created"
    action.payment_link_url = result.short_url
    action.result_json = result.normalized

    audit_action(db, action, "RAZORPAY_ADAPTER", "PAYMENT_LINK_CREATED",
                 f"Razorpay TEST Payment Link {result.payment_link_id} created for {case.case_number}",
                 {"payment_link_id": result.payment_link_id,
                  "reference_id": action.reference_id,
                  "short_url": result.short_url,
                  "amount_paise": amount_paise})
    audit_action(db, action, "ACTION_ENGINE", "ACTION_EXECUTED",
                 f"Action {action.reference_id} executed — status EXECUTED, outcome PENDING")
    audit_action(db, action, "RECON_ENGINE", "RECOVERY_PENDING",
                 f"Awaiting customer payment on Payment Link for {case.case_number} "
                 f"(revenue is NOT counted as recovered yet)")
    db.commit()
    db.refresh(action)
    logger.info("Payment Link created for %s: %s", case.case_number, result.payment_link_id)
    return action


def _block(db: Session, action: RecoveryAction, reason: str, message: str,
           *, error_code: str | None = None) -> RecoveryAction:
    action.status = "BLOCKED"
    action.blocked_reason = reason
    action.error_message = message
    if error_code:
        action.error_code = error_code
    audit_action(db, action, "ACTION_ENGINE", "ACTION_BLOCKED",
                 f"Execution blocked ({reason}): {message}",
                 {"blocked_reason": reason})
    db.commit()
    db.refresh(action)
    logger.info("Action %s BLOCKED: %s", action.reference_id, reason)
    return action
