"""
RECON OS — Phase 6, Model 4: Customer Recovery / Churn  (advisory only)

Customer-GRAIN binary classifier: given a customer's aggregated prior case
history, predict whether their next failed payment is likely to recover.
Deliberately distinct from Model 2 (which scores one case at a time using
case-level features) — this model only sees aggregate customer behavior,
never the specifics of the case being decided, and never any sensitive
demographic/medical attribute (only payment/recovery/product-interaction
history, per the Phase 6 directive).
"""

from __future__ import annotations

from sklearn.ensemble import HistGradientBoostingClassifier

from ai.features.feature_builder import CUSTOMER_CATEGORICAL_FEATURES, CUSTOMER_NUMERIC_FEATURES, FEATURE_VERSION
from ai.models.base import ModelRegistry

MODEL_NAME = "customer_recovery"
NUMERIC_FEATURES = CUSTOMER_NUMERIC_FEATURES
CATEGORICAL_FEATURES = CUSTOMER_CATEGORICAL_FEATURES


def build_estimator():
    return HistGradientBoostingClassifier(max_depth=5, max_iter=150, random_state=42)


def predict_one(features: dict) -> dict | None:
    import pandas as pd

    model, metadata = ModelRegistry.load_model(MODEL_NAME)
    if model is None or metadata is None or metadata.feature_version != FEATURE_VERSION:
        return None

    df = pd.DataFrame([features])
    proba = model.predict_proba(df)[0]
    classes = list(model.classes_)
    p = float(proba[classes.index(True)]) if True in classes else float(proba.max())
    return {
        "model_name": MODEL_NAME,
        "model_version": metadata.version,
        "status": metadata.status,
        "real_world_validation": metadata.real_world_validation,
        "customer_recovery_probability": round(p, 4),
        "customer_risk_score": round(1.0 - p, 4),
    }
