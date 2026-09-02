"""
RECON OS — Phase 10: Deterministic Intent Evaluation

RECON should recover involuntary payment failures, not unwilling customers.
This is a NEW pipeline stage — CaseContext -> Diagnosis -> Prediction ->
Strategy -> INTENT -> Policy — and answers a question distinct from both
Diagnosis (why did it fail?) and Prediction (how likely is recovery to
work?): does RECON have evidence the customer actually wants to be
recovered?

Pure function of an already-built CaseContext/DiagnosisResult/PredictionResult
— no DB access, no LLM call, no randomness. Same CaseContext in, same
IntentResult out. Never executes, never mutates anything; feeds the Policy
Engine as additional structured evidence only (see policy_engine.py
RULE_INTENT_UNWILLING / RULE_INTENT_EVIDENCE) — it can never itself approve,
reject, or bypass a policy decision.
"""

import logging
from datetime import datetime, timezone

from schemas.intelligence import (
    CaseContext,
    DiagnosisResult,
    IntentClassification,
    IntentResult,
    IntentSignal,
    PredictionResult,
)

logger = logging.getLogger("recon.services.intelligence.intent")

# Signals the directive asks for that RECON's current data model cannot
# supply — reported honestly on every evaluation, never fabricated. See the
# Phase 10 plan for why each is absent today.
UNAVAILABLE_SIGNALS = [
    "payment_link_click_tracking",       # no click/open tracking model exists
    "customer_communication_response",   # Communication.status is provider-delivery only, no inbound replies
    "mandate_subscription_state",        # RECON is one-off Payment Link recovery only, no mandate model
]

# A single expired/cancelled link or one refund does not by itself indicate
# unwillingness (could be one bad experience, or a legitimate product
# return) — only a REPEATED pattern is treated as a strong negative signal.
_REPEATED_THRESHOLD = 2


def evaluate_intent(ctx: CaseContext, diagnosis: DiagnosisResult,
                     prediction: PredictionResult,  # noqa: ARG001 - deliberately unused: recovery
                     # PROBABILITY and recovery INTENT are different questions and must not be
                     # conflated (see the Phase 10 directive); kept in the signature so callers
                     # always pass the full pipeline state, available for a future rule.
                     ) -> IntentResult:
    positive: list[IntentSignal] = []
    negative: list[IntentSignal] = []
    reason_codes: list[str] = []

    def pos(code: str, description: str):
        positive.append(IntentSignal(code=code, description=description))
        reason_codes.append(code)

    def neg(code: str, description: str):
        negative.append(IntentSignal(code=code, description=description))
        reason_codes.append(code)

    # --- Negative (unwillingness-adjacent) signals -------------------------
    if diagnosis.failure_category.value == "RISK_BLOCK":
        neg("RISK_BLOCK", "Payment was blocked by risk/fraud checks — never an automation candidate.")
    if diagnosis.failure_category.value == "USER_ABANDONED":
        neg("EXPLICIT_ABANDONMENT_SIGNAL", "This failure was itself diagnosed as a user-initiated abandonment.")
    if ctx.customer_opted_out:
        neg("EXPLICIT_OPT_OUT", "Customer has explicitly opted out of at least one communication channel.")
    if ctx.customer_prior_user_abandoned_count >= _REPEATED_THRESHOLD:
        neg("REPEATED_ABANDONMENT",
            f"Customer has {ctx.customer_prior_user_abandoned_count} prior cases diagnosed as user-abandoned.")
    if ctx.customer_expired_or_cancelled_links >= _REPEATED_THRESHOLD:
        neg("REPEATED_IGNORED_RECOVERY_ATTEMPTS",
            f"Customer let {ctx.customer_expired_or_cancelled_links} prior payment links expire/get cancelled "
            f"without paying.")
    elif ctx.customer_expired_or_cancelled_links == 1:
        # Weak signal alone — noted but not enough to move the classification.
        reason_codes.append("ONE_IGNORED_RECOVERY_ATTEMPT")
    if ctx.customer_disputed_payment_count >= 1:
        neg("DISPUTE_HISTORY", f"Customer has {ctx.customer_disputed_payment_count} disputed payment(s) on record.")

    # --- Positive (recoverable-adjacent) signals ---------------------------
    if ctx.customer_successful_payments >= 1:
        pos("PREVIOUS_SUCCESS", f"Customer has {ctx.customer_successful_payments} prior successful payment(s).")
    if ctx.attempt_count == 0:
        pos("LOW_RETRY_COUNT", "This is the first recovery attempt for this case.")
    if diagnosis.failure_category.value in ("AUTH_TIMEOUT", "TECHNICAL_GATEWAY"):
        pos("TRANSIENT_FAILURE", f"Diagnosed cause ({diagnosis.failure_category.value}) is typically transient.")
    elif diagnosis.failure_category.value in ("INSUFFICIENT_FUNDS", "BANK_DECLINE"):
        # Explicitly called out by the directive as a potentially involuntary
        # cause ("insufficient funds where recovery signals are positive") —
        # a known payment-instrument issue, not a behavioral signal, and
        # must not be treated as evidence-free just because the customer is
        # new. Only an UNKNOWN diagnosis genuinely leaves zero information.
        pos("KNOWN_NON_BEHAVIORAL_CAUSE",
            f"Diagnosed cause ({diagnosis.failure_category.value}) is a known payment-instrument "
            f"issue, not a behavioral signal.")
    if ctx.previous_resolved_cases >= 1:
        pos("PRIOR_SUCCESSFUL_RECOVERY", f"Customer has {ctx.previous_resolved_cases} previously RESOLVED recovery case(s).")

    hard_negative = bool(
        diagnosis.failure_category.value == "RISK_BLOCK"
        or ctx.customer_opted_out
        or ctx.customer_prior_user_abandoned_count >= _REPEATED_THRESHOLD
        or ctx.customer_expired_or_cancelled_links >= _REPEATED_THRESHOLD
    )

    # Evidence strong enough to decide either way — excludes ONLY
    # LOW_RETRY_COUNT, which is true of nearly every first attempt
    # (including a brand-new customer's) and so carries no real
    # information on its own. TRANSIENT_FAILURE stays counted: a clear
    # AUTH_TIMEOUT/TECHNICAL_GATEWAY diagnosis is real evidence the
    # failure was involuntary, independent of whether we've seen this
    # customer before — intent is about willingness, not familiarity, and
    # the most common real case (a first-time customer hitting a known
    # transient technical failure) must not be downgraded to
    # INSUFFICIENT_EVIDENCE purely for being new.
    non_trivial_evidence = bool(negative) or any(s.code != "LOW_RETRY_COUNT" for s in positive)
    new_or_unknown_customer = ctx.customer_id is None or not ctx.customer_has_history

    # --- Classification (ordered, deterministic) ----------------------------
    if hard_negative:
        classification = IntentClassification.LIKELY_UNWILLING
    elif new_or_unknown_customer and not non_trivial_evidence:
        classification = IntentClassification.INSUFFICIENT_EVIDENCE
    elif positive and not negative:
        classification = IntentClassification.RECOVERABLE
    else:
        classification = IntentClassification.AMBIGUOUS

    # --- Evidence completeness ----------------------------------------------
    # Fraction of the applicable signal slots that had real (non-default)
    # data available for this case — honestly computed from what's actually
    # known, never a fabricated confidence number.
    applicable_slots = [
        ctx.customer_id is not None,
        ctx.customer_has_history,
        diagnosis.failure_category.value != "UNKNOWN",
        bool(ctx.failure_code or ctx.failure_reason or ctx.failure_description),
        ctx.previous_recovery_cases > 0 or ctx.customer_has_history,
    ]
    evidence_completeness = round(sum(1 for s in applicable_slots if s) / len(applicable_slots), 4)

    # --- Confidence ----------------------------------------------------------
    confidence = 0.4
    if not new_or_unknown_customer:
        confidence += 0.2
    if hard_negative or (positive and not negative):
        confidence += 0.2  # unanimous signal direction — more confident either way
    if diagnosis.confidence >= 0.70:
        confidence += 0.1
    if classification == IntentClassification.INSUFFICIENT_EVIDENCE:
        confidence = min(confidence, 0.5)  # never claim high confidence with no evidence
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    positives_str = ", ".join(s.code for s in positive) or "none"
    negatives_str = ", ".join(s.code for s in negative) or "none"
    rationale = (
        f"Classified as {classification.value} (confidence {confidence:.0%}, "
        f"evidence completeness {evidence_completeness:.0%}). "
        f"Positive signals: {positives_str}. Negative signals: {negatives_str}."
    )

    return IntentResult(
        classification=classification,
        confidence=confidence,
        reason_codes=reason_codes,
        positive_signals=positive,
        negative_signals=negative,
        unavailable_signals=list(UNAVAILABLE_SIGNALS),
        evidence_completeness=evidence_completeness,
        rationale=rationale,
        provider="DETERMINISTIC",
        provider_version=None,
        evaluated_at=datetime.now(timezone.utc),
    )
