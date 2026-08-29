"""
RECON OS — Phase 2: Deterministic Recovery Prediction

An additive, explainable scorecard:

    recovery_probability = clamp( base_rate(failure_category) + Σ contributions )

Same CaseContext + Diagnosis in  ->  same prediction out. No randomness, no
time-based seeds, no hardcoded "84%" outputs. Every contribution is returned in
`features_used` so the number is fully traceable. This stays deterministic even
if an LLM is later attached to diagnosis.
"""

import logging

from schemas.intelligence import (
    CaseContext,
    DiagnosisResult,
    FeatureContribution,
    PredictionBand,
    PredictionResult,
)
from services.intelligence import weights

logger = logging.getLogger("recon.services.intelligence.prediction")


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def predict(ctx: CaseContext, diagnosis: DiagnosisResult) -> PredictionResult:
    category = diagnosis.failure_category.value
    base_rate = weights.PREDICTION_BASE_RATE.get(
        category, weights.PREDICTION_BASE_RATE["UNKNOWN"]
    )

    features: list[FeatureContribution] = []

    def add(feature: str, value: str, contribution: float, note: str | None = None):
        contribution = round(contribution, 4)
        direction = (
            "positive" if contribution > 0
            else "negative" if contribution < 0
            else "neutral"
        )
        features.append(FeatureContribution(
            feature=feature, value=value, contribution=contribution,
            direction=direction, note=note,
        ))
        return contribution

    score = base_rate
    features.append(FeatureContribution(
        feature="failure_category_base_rate", value=category,
        contribution=round(base_rate, 4), direction="neutral",
        note="Historical baseline recoverability for this failure category",
    ))

    # 1. Customer success rate
    settled = ctx.customer_successful_payments + ctx.customer_failed_payments
    if settled >= weights.PREDICTION_MIN_HISTORY_FOR_RATE:
        contrib = (ctx.customer_success_rate - 0.5) * weights.PREDICTION_W_SUCCESS_RATE
        score += add(
            "customer_success_rate",
            f"{ctx.customer_success_rate:.0%} ({ctx.customer_successful_payments}/{settled} settled)",
            contrib,
        )
    else:
        add(
            "customer_success_rate",
            f"insufficient history ({settled} settled payment(s))",
            0.0,
            "Neutral — not enough payment history to trust a success rate",
        )

    # 2. Attempt count
    ac = ctx.attempt_count
    if ac >= weights.PREDICTION_ATTEMPT_CONTRIB_EXHAUSTED and ac >= 3:
        attempt_contrib = weights.PREDICTION_ATTEMPT_CONTRIB_EXHAUSTED
    else:
        attempt_contrib = weights.PREDICTION_ATTEMPT_CONTRIB.get(
            ac, weights.PREDICTION_ATTEMPT_CONTRIB_EXHAUSTED
        )
    score += add("attempt_count", str(ac), attempt_contrib)

    # 3. Amount band
    amt_contrib = weights.PREDICTION_AMOUNT_CONTRIB.get(ctx.amount_band, 0.0)
    score += add(
        "amount_band",
        f"{ctx.amount_band} ({ctx.currency} {ctx.amount})",
        amt_contrib,
    )

    # 4. Payment method
    method = (ctx.payment_method or "unknown").lower()
    method_contrib = weights.PREDICTION_METHOD_CONTRIB.get(method, 0.0)
    score += add("payment_method", method, method_contrib)

    # 5. Time since failure (coarse buckets — monotonic, deterministic)
    recency_contrib = weights.prediction_recency_contribution(ctx.hours_since_failure)
    score += add(
        "time_since_failure",
        f"{ctx.hours_since_failure:.1f}h",
        recency_contrib,
    )

    # 6. Prior recovery outcomes for this customer
    if ctx.previous_resolved_cases >= 1:
        score += add(
            "prior_resolved_cases",
            str(ctx.previous_resolved_cases),
            weights.PREDICTION_PRIOR_RESOLVED_BONUS,
            "Customer has previously been recovered successfully",
        )
    prior_unresolved = ctx.previous_recovery_cases - ctx.previous_resolved_cases
    if prior_unresolved >= 1:
        score += add(
            "prior_unresolved_cases",
            str(prior_unresolved),
            weights.PREDICTION_PRIOR_UNRESOLVED_PENALTY,
            "Customer has prior recovery cases that were never resolved",
        )

    probability = _clamp(
        round(score, 4),
        weights.PREDICTION_PROBABILITY_MIN,
        weights.PREDICTION_PROBABILITY_MAX,
    )

    if probability >= weights.PREDICTION_BAND_HIGH_MIN:
        band = PredictionBand.HIGH
    elif probability >= weights.PREDICTION_BAND_MEDIUM_MIN:
        band = PredictionBand.MEDIUM
    else:
        band = PredictionBand.LOW

    # Confidence: how much do we trust this estimate?
    conf = weights.PREDICTION_CONFIDENCE_BASE
    if ctx.customer_has_history:
        conf += weights.PREDICTION_CONFIDENCE_HAS_HISTORY
    if diagnosis.confidence >= 0.70:
        conf += weights.PREDICTION_CONFIDENCE_STRONG_DIAGNOSIS
    if ctx.attempt_count == 0:
        conf += weights.PREDICTION_CONFIDENCE_FIRST_ATTEMPT
    if ctx.failure_code:
        conf += weights.PREDICTION_CONFIDENCE_HAS_ERROR_CODE
    conf = _clamp(
        round(conf, 4),
        weights.PREDICTION_CONFIDENCE_MIN,
        weights.PREDICTION_CONFIDENCE_MAX,
    )

    positives = [f.feature for f in features if f.direction == "positive"]
    negatives = [f.feature for f in features if f.direction == "negative"]
    rationale = (
        f"Base recoverability for {category} is {base_rate:.0%}. "
        f"Adjusted to {probability:.0%} ({band.value}). "
        f"Positive factors: {', '.join(positives) or 'none'}. "
        f"Negative factors: {', '.join(negatives) or 'none'}."
    )

    return PredictionResult(
        recovery_probability=probability,
        band=band,
        confidence=conf,
        base_rate=round(base_rate, 4),
        features_used=features,
        rationale=rationale,
        provider="DETERMINISTIC",
    )
