"""
RECON OS — Phase 6, Model 3: Recovery Time Prediction  (advisory, EXPERIMENTAL)

Regression: expected hours until recovery, trained ONLY on rows where
`recovered == True` (recovery_hours is undefined otherwise — not zero-filled,
which would fabricate a false signal). Real `recon_dev.db` currently has
only 13 RECOVERED actions with a completed_at/requested_at pair, far too few
for a trustworthy regression — this model is trained on the synthetic
dataset and its metadata is marked EXPERIMENTAL; see ai/training/train.py
for the exact real-sample count found at training time.
"""

from __future__ import annotations

from sklearn.ensemble import HistGradientBoostingRegressor

from ai.features.feature_builder import CASE_CATEGORICAL_FEATURES, CASE_NUMERIC_FEATURES, FEATURE_VERSION
from ai.models.base import ModelRegistry

MODEL_NAME = "recovery_time"
NUMERIC_FEATURES = CASE_NUMERIC_FEATURES
CATEGORICAL_FEATURES = CASE_CATEGORICAL_FEATURES


def build_estimator():
    return HistGradientBoostingRegressor(max_depth=5, max_iter=150, random_state=42)


def predict_one(features: dict) -> dict | None:
    import pandas as pd

    model, metadata = ModelRegistry.load_model(MODEL_NAME)
    if model is None or metadata is None or metadata.feature_version != FEATURE_VERSION:
        return None

    df = pd.DataFrame([features])
    hours = float(model.predict(df)[0])
    return {
        "model_name": MODEL_NAME,
        "model_version": metadata.version,
        "status": metadata.status,   # expected "EXPERIMENTAL" — surface this to callers
        "expected_recovery_hours": round(max(hours, 0.0), 2),
    }
