"""
RECON OS — Phase 6, Model 2: Recovery Probability  (advisory only)

Binary classifier: P(outcome == RECOVERED) given case features (post-
diagnosis). This is a genuine ML signal alongside the existing deterministic
additive scorecard in services/intelligence/prediction.py — it does NOT
replace `PredictionResult.recovery_probability`, which remains what the
Policy Engine and every downstream safety check reads. The ML value is
attached separately as `ml_predictions_json.recovery_probability`.
"""

from __future__ import annotations

from sklearn.ensemble import HistGradientBoostingClassifier

from ai.features.feature_builder import CASE_CATEGORICAL_FEATURES, CASE_NUMERIC_FEATURES, FEATURE_VERSION
from ai.models.base import ModelRegistry

MODEL_NAME = "recovery_probability"
NUMERIC_FEATURES = CASE_NUMERIC_FEATURES
CATEGORICAL_FEATURES = CASE_CATEGORICAL_FEATURES


def build_estimator():
    return HistGradientBoostingClassifier(max_depth=6, max_iter=200, random_state=42)


def predict_one(features: dict) -> dict | None:
    import pandas as pd

    model, metadata = ModelRegistry.load_model(MODEL_NAME)
    if model is None or metadata is None or metadata.feature_version != FEATURE_VERSION:
        return None

    df = pd.DataFrame([features])
    proba = model.predict_proba(df)[0]
    classes = list(model.classes_)
    p_recovered = float(proba[classes.index(True)]) if True in classes else float(proba.max())
    return {
        "model_name": MODEL_NAME,
        "model_version": metadata.version,
        "status": metadata.status,
        "real_world_validation": metadata.real_world_validation,
        "recovery_probability": round(p_recovered, 4),
    }
