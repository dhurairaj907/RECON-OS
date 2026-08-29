"""
RECON OS — Phase 2: Deterministic Diagnosis Engine

Maps real Razorpay failure information (error_code / error_reason /
error_description / payment method / payment state) onto a controlled set of
failure categories. This is NOT an LLM result — it is a transparent keyword +
rule classifier. `provider` is reported as "DETERMINISTIC".
"""

import logging

from schemas.intelligence import CaseContext, DiagnosisResult, FailureCategory
from services.intelligence import weights

logger = logging.getLogger("recon.services.intelligence.diagnosis")


def _haystack(ctx: CaseContext) -> str:
    parts = [
        ctx.failure_code or "",
        ctx.failure_reason or "",
        ctx.failure_description or "",
    ]
    return " ".join(p.lower() for p in parts if p)


def diagnose(ctx: CaseContext) -> DiagnosisResult:
    text = _haystack(ctx)
    method = (ctx.payment_method or "").lower().strip()
    reason = (ctx.failure_reason or "").lower().strip()
    code = (ctx.failure_code or "").upper().strip()

    evidence: list[str] = []
    if ctx.failure_code:
        evidence.append(f"error_code = {ctx.failure_code}")
    if ctx.failure_reason:
        evidence.append(f"error_reason = {ctx.failure_reason}")
    if ctx.failure_description:
        evidence.append(f"error_description = \"{ctx.failure_description}\"")
    if method:
        evidence.append(f"payment_method = {method}")
    if ctx.payment_status:
        evidence.append(f"payment_status = {ctx.payment_status}")

    # 1. Explicit reason overrides (highest trust)
    if reason in weights.DIAGNOSIS_REASON_OVERRIDES:
        category, conf = weights.DIAGNOSIS_REASON_OVERRIDES[reason]
        return _build(
            category, conf, ctx, evidence,
            matched=[f"error_reason='{reason}'"],
        )

    # 2. Ordered keyword rules (order = priority, risk first)
    best = None  # (category, matched_keywords)
    for category, keywords in weights.DIAGNOSIS_KEYWORD_RULES:
        matched = [kw for kw in keywords if kw in text]
        if matched:
            best = (category, matched)
            break

    if best is not None:
        category, matched = best
        conf = weights.DIAGNOSIS_BASE_CONFIDENCE[category]
        if len(set(matched)) >= 2:
            conf += weights.DIAGNOSIS_MULTI_KEYWORD_BONUS
        # method corroboration for timeout / gateway on UPI
        if category in ("AUTH_TIMEOUT", "TECHNICAL_GATEWAY") and method == "upi":
            conf += weights.DIAGNOSIS_METHOD_CORROBORATION_BONUS
        conf = min(conf, weights.DIAGNOSIS_CONFIDENCE_CAP)
        return _build(
            category, conf, ctx, evidence,
            matched=[f"keyword '{kw}'" for kw in matched],
        )

    # 3. Known error_code fallback
    if code in weights.DIAGNOSIS_ERROR_CODE_FALLBACK:
        category, conf = weights.DIAGNOSIS_ERROR_CODE_FALLBACK[code]
        return _build(
            category, conf, ctx, evidence,
            matched=[f"error_code fallback '{code}'"],
        )

    # 4. Unknown
    return _build(
        "UNKNOWN",
        weights.DIAGNOSIS_BASE_CONFIDENCE["UNKNOWN"],
        ctx,
        evidence,
        matched=["no diagnostic keywords or known codes matched"],
    )


def _build(category: str, confidence: float, ctx: CaseContext,
           evidence: list[str], matched: list[str]) -> DiagnosisResult:
    confidence = max(0.0, min(1.0, round(confidence, 4)))
    probable_cause = weights.PROBABLE_CAUSE[category]
    rationale = (
        f"Classified as {category} (confidence {confidence:.0%}). "
        f"Basis: {'; '.join(matched)}."
    )
    return DiagnosisResult(
        failure_category=FailureCategory(category),
        probable_cause=probable_cause,
        confidence=confidence,
        rationale=rationale,
        evidence=evidence + matched,
        provider="DETERMINISTIC",
    )
