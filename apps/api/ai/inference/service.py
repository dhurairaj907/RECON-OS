"""
RECON OS — Phase 6: AI Inference Service  (SAFETY: advisory only, read-only)

    Case -> Feature Builder -> Model Registry -> Model Inference -> Prediction
         -> attached to CaseIntelligence.ml_predictions_json
         -> Policy Engine / Action Engine (UNCHANGED, still authoritative)

This module has ZERO knowledge of the Razorpay adapter, the Action Engine,
or the Communication provider — it cannot reach them even by accident. It
returns a plain dict of predictions; what (if anything) happens with that
dict is entirely the existing orchestrator/Policy Engine/Action Engine's
decision, unchanged by Phase 6.

Every call is deterministic for a given (model version, input): scikit-learn
inference has no randomness at predict time. Every prediction is tagged with
its model_name/model_version/status so it's traceable — see
orchestrator.py's audit write for how this becomes part of the case's
permanent record.

If a model artifact is missing/stale (feature_version mismatch), its key is
simply omitted from the result — this function NEVER raises for a missing
model and NEVER fabricates a value in its place.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from ai.features.feature_builder import (
    FEATURE_VERSION, build_case_features, build_customer_features,
    build_diagnosis_features, context_to_source,
)
from ai.models import channel_model, churn_model, diagnosis_model, expected_value
from ai.models import recovery_probability_model, recovery_time_model, strategy_ranking_model, response_model
from ai.models.anomaly_model import load_latest as load_anomaly_model

logger = logging.getLogger("recon.ai.inference")

REAL_CHANNELS = ("EMAIL", "SMS", "WHATSAPP")


def _available_channels(customer: Optional[dict]) -> list[str]:
    """Filters to channels the customer actually has contact info for and has
    NOT opted out of — mirrors services/communications/service.py's own
    contact/opt-out checks so the model never recommends an unreachable
    channel. `customer` is a plain dict: {email, phone, opted_out_channels}."""
    if customer is None:
        return list(REAL_CHANNELS)   # unknown customer context — advisory default, caller still gates the real send
    opted_out = {c.strip().upper() for c in (customer.get("opted_out_channels") or "").split(",") if c.strip()}
    out = []
    if customer.get("email") and "EMAIL" not in opted_out:
        out.append("EMAIL")
    if customer.get("phone") and "SMS" not in opted_out:
        out.append("SMS")
    if customer.get("phone") and "WHATSAPP" not in opted_out:
        out.append("WHATSAPP")
    return out


def predict_for_case(ctx, *, failure_category: str, customer: Optional[dict] = None) -> dict:
    """
    Runs every available trained model for one case. `ctx` is the same
    `CaseContext` the deterministic pipeline already built (Phase 2) —
    nothing here re-derives case state independently. `failure_category` is
    the diagnosis ALREADY produced by the deterministic/AI diagnosis step
    (never invented here). `customer` optionally carries contact/opt-out info
    (plain dict) so channel recommendations respect it — see
    _available_channels above.

    Returns a plain dict; never raises for a missing/stale model artifact.
    """
    source = context_to_source(ctx)
    amount = float(source.get("amount") or 0)
    predictions: dict = {
        "feature_version": FEATURE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        diag_features = build_diagnosis_features(source)
        result = diagnosis_model.predict_one(diag_features)
        if result:
            predictions["diagnosis"] = result
    except Exception:
        logger.exception("diagnosis model inference failed (non-fatal)")

    case_features = build_case_features(source, failure_category=failure_category)

    for name, fn in (
        ("recovery_probability", recovery_probability_model.predict_one),
        ("recovery_time", recovery_time_model.predict_one),
    ):
        try:
            result = fn(case_features)
            if result:
                predictions[name] = result
        except Exception:
            logger.exception("%s model inference failed (non-fatal)", name)

    try:
        prev_cases = int(source.get("previous_recovery_cases") or 0)
        prev_resolved = int(source.get("previous_resolved_cases") or 0)
        successful_payments = int(source.get("customer_successful_payments") or 0)
        failed_payments = int(source.get("customer_failed_payments") or 0)
        settled_payments = successful_payments + failed_payments
        lifetime_amount = float(source.get("customer_lifetime_amount") or 0)
        # Genuine historical average-per-payment derived from this customer's
        # REAL settled payment history (customer_lifetime_amount / count) —
        # not the current case's amount. Falls back to the current case
        # amount ONLY when the customer has zero payment history at all (a
        # brand-new customer), where it's the sole honest estimate available,
        # never silently substituted for a customer we DO have history for.
        avg_amount = (lifetime_amount / settled_payments) if settled_payments > 0 else amount
        customer_features = build_customer_features({
            "total_prior_cases": prev_cases,
            "prior_recovered_count": prev_resolved,
            "prior_recovery_rate": (prev_resolved / prev_cases) if prev_cases else float(source.get("customer_success_rate") or 0.0),
            "avg_amount": avg_amount,
            "customer_success_rate": source.get("customer_success_rate", 0.0),
            "customer_lifetime_amount": source.get("customer_lifetime_amount", 0),
            "customer_has_history": source.get("customer_has_history", False),
            "amount_band": source.get("amount_band", "UNKNOWN"),
            "payment_method": source.get("payment_method", "unknown"),
            "failure_category": failure_category,
        })
        result = churn_model.predict_one(customer_features)
        if result:
            predictions["customer_recovery"] = result
    except Exception:
        logger.exception("customer_recovery model inference failed (non-fatal)")

    try:
        anomaly_model, anomaly_meta = load_anomaly_model()
        if anomaly_model and anomaly_meta and anomaly_meta.feature_version == FEATURE_VERSION:
            import pandas as pd
            df = pd.DataFrame([case_features])
            predictions["anomaly"] = {
                "model_name": "anomaly", "model_version": anomaly_meta.version, "status": anomaly_meta.status,
                "real_world_validation": anomaly_meta.real_world_validation,
                "anomaly_score": round(float(anomaly_model.score(df)[0]), 4),
                "is_anomaly": bool(anomaly_model.predict_is_anomaly(df)[0]),
            }
    except Exception:
        logger.exception("anomaly model inference failed (non-fatal)")

    strategy_ranking = None
    try:
        strategy_ranking = strategy_ranking_model.rank_strategies(case_features)
        if strategy_ranking:
            predictions["strategy_ranking"] = strategy_ranking
    except Exception:
        logger.exception("strategy_ranking model inference failed (non-fatal)")

    if strategy_ranking and amount > 0:
        try:
            predictions["expected_recovery_value"] = {
                "basis": "strategy",
                "ranking": expected_value.compute_strategy_expected_values(amount, strategy_ranking["ranking"]),
            }
        except Exception:
            logger.exception("expected_recovery_value (strategy) calculation failed (non-fatal)")

    candidates = _available_channels(customer)
    channel_ranking = None
    try:
        channel_ranking = channel_model.rank_channels(
            case_features, message_type="PAYMENT_LINK_CREATED",
            prior_communications_24h=int(source.get("customer_contacts_last_24h") or 0),
            candidate_channels=candidates,
        )
        if channel_ranking:
            predictions["communication_channel"] = channel_ranking
    except Exception:
        logger.exception("communication_channel model inference failed (non-fatal)")

    if channel_ranking and channel_ranking["ranking"] and amount > 0:
        try:
            predictions["channel_expected_value"] = expected_value.compute_channel_expected_values(
                amount, channel_ranking["ranking"]
            )
        except Exception:
            logger.exception("expected_recovery_value (channel) calculation failed (non-fatal)")

    if channel_ranking and channel_ranking["ranking"]:
        top_channel = channel_ranking["ranking"][0]["channel"]
        try:
            result = response_model.predict_one(
                case_features, channel=top_channel, message_type="PAYMENT_LINK_CREATED",
                prior_communications_24h=int(source.get("customer_contacts_last_24h") or 0),
            )
            if result:
                predictions["message_response"] = result
        except Exception:
            logger.exception("message_response model inference failed (non-fatal)")

    return predictions
