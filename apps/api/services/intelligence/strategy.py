"""
RECON OS — Phase 2: Deterministic Strategy Selector

Recommends ONE recovery action from the controlled action set. It only
*recommends* — it never executes anything, and the recommendation is always
passed to the Policy Engine afterwards. Selection is a transparent decision
tree over (diagnosis, prediction band, amount band, method, attempt count,
customer history).
"""

import logging

from schemas.intelligence import (
    CaseContext,
    DiagnosisResult,
    PredictionBand,
    PredictionResult,
    StrategyAction,
    StrategyAlternative,
    StrategyResult,
)
from services.intelligence import weights

logger = logging.getLogger("recon.services.intelligence.strategy")


def recommend_strategy(
    ctx: CaseContext,
    diagnosis: DiagnosisResult,
    prediction: PredictionResult,
) -> StrategyResult:
    category = diagnosis.failure_category.value
    band = prediction.band
    attempts_left = ctx.max_attempts - ctx.attempt_count
    params: dict = {}
    alternatives: list[StrategyAlternative] = []

    # --- Rule 0: risk / fraud is never an automation candidate ------------
    if category == "RISK_BLOCK":
        action = StrategyAction.MANUAL_REVIEW
        rationale = (
            "Risk/fraud-blocked payment. No automated retry or customer contact "
            "may be recommended — a human must investigate before any action."
        )
        return _finalise(action, params, rationale, diagnosis, prediction,
                         alternatives=[
                             StrategyAlternative(action=StrategyAction.NO_ACTION,
                                                 reason="Close the case if the block is confirmed legitimate")
                         ])

    # --- Rule 1: attempts exhausted --------------------------------------
    if attempts_left <= 0:
        action = StrategyAction.NO_ACTION
        rationale = (
            f"Maximum recovery attempts reached ({ctx.attempt_count}/{ctx.max_attempts}). "
            "No further automated recovery is appropriate."
        )
        return _finalise(action, params, rationale, diagnosis, prediction,
                         alternatives=[
                             StrategyAlternative(action=StrategyAction.MANUAL_REVIEW,
                                                 reason="Escalate to a human if the amount justifies manual follow-up")
                         ])

    # --- Category-specific selection ------------------------------------
    if category == "INSUFFICIENT_FUNDS":
        if band == PredictionBand.LOW:
            action = StrategyAction.CUSTOMER_OUTREACH
            params = {"channel": weights.STRATEGY_OUTREACH_CHANNEL,
                      "message_intent": "funds_reminder"}
            rationale = ("Insufficient funds with low recovery probability — a gentle "
                         "reminder to the customer is the safest next step.")
            alternatives = [StrategyAlternative(action=StrategyAction.RETRY_DELAYED,
                                                reason="Retry after a few days once salary/credit cycles refresh")]
        else:
            action = StrategyAction.RETRY_DELAYED
            params = {"delay_hours": weights.STRATEGY_RETRY_DELAY_HOURS_FUNDS}
            rationale = ("Insufficient funds — wait for the customer's balance to "
                         f"refresh, then retry after ~{weights.STRATEGY_RETRY_DELAY_HOURS_FUNDS}h.")
            alternatives = [StrategyAlternative(action=StrategyAction.SEND_PAYMENT_LINK,
                                                reason="Let the customer choose another instrument")]

    elif category == "BANK_DECLINE":
        if band == PredictionBand.HIGH:
            action = StrategyAction.RETRY_DELAYED
            params = {"delay_hours": weights.STRATEGY_RETRY_DELAY_HOURS_DEFAULT}
            rationale = "Bank decline but strong recovery signal — a delayed retry often clears transient issuer blocks."
            alternatives = [StrategyAlternative(action=StrategyAction.SEND_PAYMENT_LINK,
                                                reason="Offer an alternate payment method")]
        elif band == PredictionBand.MEDIUM:
            action = StrategyAction.SEND_PAYMENT_LINK
            params = {"channel": weights.STRATEGY_PAYMENT_LINK_CHANNEL}
            rationale = "Bank decline — the same instrument is likely to fail again; offer the customer an alternate method."
            alternatives = [StrategyAlternative(action=StrategyAction.CUSTOMER_OUTREACH,
                                                reason="Explain the decline and ask the customer to contact their bank")]
        else:
            action = StrategyAction.CUSTOMER_OUTREACH
            params = {"channel": weights.STRATEGY_OUTREACH_CHANNEL,
                      "message_intent": "bank_decline_help"}
            rationale = "Bank decline with weak recovery signal — inform the customer and let them resolve it with their bank."

    elif category in ("AUTH_TIMEOUT", "TECHNICAL_GATEWAY"):
        if band == PredictionBand.HIGH and ctx.attempt_count == 0:
            action = StrategyAction.RETRY_NOW
            rationale = ("Transient technical/authorisation failure, first attempt, high recovery "
                         "probability — an immediate retry is the highest-value action.")
            alternatives = [StrategyAlternative(action=StrategyAction.RETRY_DELAYED,
                                                reason="If an immediate retry also fails, back off and retry later")]
        elif band in (PredictionBand.HIGH, PredictionBand.MEDIUM):
            action = StrategyAction.RETRY_DELAYED
            params = {"delay_hours": weights.STRATEGY_RETRY_DELAY_HOURS_TECHNICAL}
            rationale = ("Technical/authorisation failure — back off briefly to let the gateway "
                         f"recover, then retry after ~{weights.STRATEGY_RETRY_DELAY_HOURS_TECHNICAL}h.")
            alternatives = [StrategyAlternative(action=StrategyAction.SEND_PAYMENT_LINK,
                                                reason="Give the customer a fresh checkout link")]
        else:
            action = StrategyAction.SEND_PAYMENT_LINK
            params = {"channel": weights.STRATEGY_PAYMENT_LINK_CHANNEL}
            rationale = "Repeated/low-confidence technical failure — hand the customer a fresh payment link."

    elif category == "USER_ABANDONED":
        if band in (PredictionBand.HIGH, PredictionBand.MEDIUM):
            action = StrategyAction.SEND_PAYMENT_LINK
            params = {"channel": weights.STRATEGY_PAYMENT_LINK_CHANNEL}
            rationale = "Customer dropped off mid-payment — a payment link makes it easy to resume."
            alternatives = [StrategyAlternative(action=StrategyAction.CUSTOMER_OUTREACH,
                                                reason="A nudge reminding them to complete the purchase")]
        else:
            action = StrategyAction.CUSTOMER_OUTREACH
            params = {"channel": weights.STRATEGY_OUTREACH_CHANNEL,
                      "message_intent": "cart_reminder"}
            rationale = "Customer abandoned the payment with a weak recovery signal — a single reminder is proportionate."

    else:  # UNKNOWN
        if band == PredictionBand.HIGH:
            action = StrategyAction.RETRY_DELAYED
            params = {"delay_hours": weights.STRATEGY_RETRY_DELAY_HOURS_DEFAULT}
            rationale = "Cause unclear but recovery signal is strong — a single delayed retry is a reasonable low-risk attempt."
        else:
            action = StrategyAction.MANUAL_REVIEW
            rationale = "Failure cause could not be determined and the recovery signal is not strong — route to a human."

    return _finalise(action, params, rationale, diagnosis, prediction, alternatives)


def _finalise(action, params, rationale, diagnosis, prediction, alternatives):
    # Strategy confidence blends how sure we are about the cause and the outcome.
    confidence = round(
        max(0.0, min(1.0, 0.5 * diagnosis.confidence + 0.5 * prediction.confidence)),
        4,
    )
    if prediction.band == PredictionBand.LOW:
        confidence = round(max(0.0, confidence - 0.05), 4)
    return StrategyResult(
        action=action,
        params=params,
        rationale=rationale,
        confidence=confidence,
        alternatives=alternatives,
        provider="DETERMINISTIC",
    )
