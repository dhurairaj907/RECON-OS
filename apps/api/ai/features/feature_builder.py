"""
RECON OS — Phase 6: Feature Engineering  (single source of truth)

Used identically by synthetic data generation, real-data extraction, and live
inference — the SAME function computes features whether the source is a
freshly-built `CaseContext` at inference time, a synthetic row, or a row
pulled from `recon_dev.db`. This is what keeps training/serving skew
impossible: there is only one feature-computation code path.

Leakage discipline: every feature here comes from `CaseContext` (Phase 2's
already-audited "only what's knowable before a decision" snapshot) or from
information available at or before the moment a prediction is made. Nothing
here reads a field that would only exist AFTER the outcome being predicted
(e.g. `recovered_amount`, `completed_at`, provider results).

`FEATURE_VERSION` must be bumped whenever the feature SET or computation
changes — every trained model records the version it was trained with, and
the inference service refuses to serve a model whose feature_version doesn't
match the running code (see ai/inference/service.py).
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional

from services.intelligence.weights import DIAGNOSIS_KEYWORD_RULES

FEATURE_VERSION = "1.0"

# --- Case-level feature set (models 2, 3, 4, 6, 8, 9 — run AFTER diagnosis) ---
CASE_NUMERIC_FEATURES = [
    "amount_log",
    "attempt_count",
    "attempts_remaining",
    "hours_since_failure",
    "customer_success_rate",
    "customer_lifetime_amount_log",
    "customer_settled_payments",
    "previous_recovery_cases",
    "previous_resolved_cases",
    "previous_recovery_attempts",
    "customer_contacts_last_24h",
    "customer_has_history_int",
]
CASE_CATEGORICAL_FEATURES = ["payment_method", "failure_category", "amount_band"]
CASE_FEATURE_COLUMNS = CASE_NUMERIC_FEATURES + CASE_CATEGORICAL_FEATURES

# --- Diagnosis-only feature set (model 1 — MUST NOT see failure_category, the target) ---
_KEYWORD_GROUPS = [name for name, _ in DIAGNOSIS_KEYWORD_RULES]
DIAGNOSIS_NUMERIC_FEATURES = ["amount_log"] + [f"kw_{g.lower()}" for g in _KEYWORD_GROUPS]
DIAGNOSIS_CATEGORICAL_FEATURES = ["payment_method", "amount_band"]
DIAGNOSIS_FEATURE_COLUMNS = DIAGNOSIS_NUMERIC_FEATURES + DIAGNOSIS_CATEGORICAL_FEATURES


def _get(source: Mapping[str, Any], key: str, default=None):
    v = source.get(key, default)
    return default if v is None else v


def _safe_log1p(value: float) -> float:
    v = float(value or 0.0)
    return math.log1p(max(v, 0.0))


def build_case_features(source: Mapping[str, Any], *, failure_category: str) -> dict:
    """
    General-purpose case feature vector — used by models 2 (recovery
    probability), 3 (recovery time), 4 (churn, aggregated), 6 (strategy
    ranking), 8 (channel), 9 (message response). `failure_category` is passed
    explicitly since it's a DIAGNOSIS OUTPUT, not a raw CaseContext field —
    callers must supply the already-diagnosed category, never a placeholder.
    """
    amount = float(_get(source, "amount", 0) or 0)
    lifetime = float(_get(source, "customer_lifetime_amount", 0) or 0)
    successful = int(_get(source, "customer_successful_payments", 0) or 0)
    failed = int(_get(source, "customer_failed_payments", 0) or 0)
    attempt_count = int(_get(source, "attempt_count", 0) or 0)
    max_attempts = int(_get(source, "max_attempts", 3) or 3)

    return {
        "amount_log": _safe_log1p(amount),
        "attempt_count": attempt_count,
        "attempts_remaining": max(0, max_attempts - attempt_count),
        "hours_since_failure": float(_get(source, "hours_since_failure", 0.0) or 0.0),
        "customer_success_rate": float(_get(source, "customer_success_rate", 0.0) or 0.0),
        "customer_lifetime_amount_log": _safe_log1p(lifetime),
        "customer_settled_payments": successful + failed,
        "previous_recovery_cases": int(_get(source, "previous_recovery_cases", 0) or 0),
        "previous_resolved_cases": int(_get(source, "previous_resolved_cases", 0) or 0),
        "previous_recovery_attempts": int(_get(source, "previous_recovery_attempts", 0) or 0),
        "customer_contacts_last_24h": int(_get(source, "customer_contacts_last_24h", 0) or 0),
        "customer_has_history_int": int(bool(_get(source, "customer_has_history", False))),
        "payment_method": str(_get(source, "payment_method", "unknown") or "unknown").lower(),
        "failure_category": str(failure_category or "UNKNOWN").upper(),
        "amount_band": str(_get(source, "amount_band", "UNKNOWN") or "UNKNOWN").upper(),
    }


def build_diagnosis_features(source: Mapping[str, Any]) -> dict:
    """
    Feature vector for Model 1 (failure diagnosis). Deliberately excludes
    `failure_category` (the prediction target) — uses only text-derived
    keyword-group indicators (same keyword lists the deterministic diagnosis
    engine already uses, services/intelligence/weights.py — reused, not
    duplicated) plus payment_method/amount, all of which are known BEFORE
    diagnosis runs.
    """
    text = " ".join(
        str(_get(source, k, "") or "").lower()
        for k in ("failure_reason", "failure_description", "failure_code")
    )
    amount = float(_get(source, "amount", 0) or 0)

    features: dict = {"amount_log": _safe_log1p(amount)}
    for group_name, keywords in DIAGNOSIS_KEYWORD_RULES:
        features[f"kw_{group_name.lower()}"] = int(any(kw in text for kw in keywords))

    features["payment_method"] = str(_get(source, "payment_method", "unknown") or "unknown").lower()
    features["amount_band"] = str(_get(source, "amount_band", "UNKNOWN") or "UNKNOWN").upper()
    return features


# --- Customer-level feature set (model 4 — churn/customer recovery, aggregated grain) ---
CUSTOMER_NUMERIC_FEATURES = [
    "total_prior_cases",
    "prior_recovered_count",
    "prior_recovery_rate",
    "avg_amount_log",
    "customer_success_rate",
    "customer_lifetime_amount_log",
    "customer_has_history_int",
]
CUSTOMER_CATEGORICAL_FEATURES = ["amount_band", "payment_method", "failure_category"]
CUSTOMER_FEATURE_COLUMNS = CUSTOMER_NUMERIC_FEATURES + CUSTOMER_CATEGORICAL_FEATURES


def build_customer_features(source: Mapping[str, Any]) -> dict:
    """Aggregate-grain counterpart to `build_case_features` — same log/ratio
    transform conventions, applied to a customer-level row (see
    ai/data/synthetic.py:generate_customer_dataset)."""
    return {
        "total_prior_cases": int(_get(source, "total_prior_cases", 0) or 0),
        "prior_recovered_count": int(_get(source, "prior_recovered_count", 0) or 0),
        "prior_recovery_rate": float(_get(source, "prior_recovery_rate", 0.0) or 0.0),
        "avg_amount_log": _safe_log1p(float(_get(source, "avg_amount", 0) or 0)),
        "customer_success_rate": float(_get(source, "customer_success_rate", 0.0) or 0.0),
        "customer_lifetime_amount_log": _safe_log1p(float(_get(source, "customer_lifetime_amount", 0) or 0)),
        "customer_has_history_int": int(bool(_get(source, "customer_has_history", False))),
        "amount_band": str(_get(source, "amount_band", "UNKNOWN") or "UNKNOWN").upper(),
        "payment_method": str(_get(source, "payment_method", "unknown") or "unknown").lower(),
        "failure_category": str(_get(source, "failure_category", "UNKNOWN") or "UNKNOWN").upper(),
    }


def context_to_source(ctx) -> dict:
    """Adapts a live `CaseContext` (pydantic) into the plain-dict shape every
    feature function expects — the one conversion point between Phase 2's
    typed context and Phase 6's feature layer."""
    return ctx.model_dump(mode="json") if hasattr(ctx, "model_dump") else dict(ctx)
