"""
RECON OS — Phase 6, Model 9: Message Response / Recovery  (advisory, DATA-LIMITED)

Point prediction: given a specific already-chosen (channel, message_type,
prior_communications_24h), what's the probability the customer responds/
recovers? Used by the expected-value calculation (Model 7) for a message
that's about to be sent, distinct from Model 8's job of choosing WHICH
channel in the first place.

Real `communications` rows in recon_dev.db number in the single digits as of
Phase 6 (Phase 5 only just introduced the table) — nowhere near enough for a
trustworthy model of real customer response behavior. Trained on the
synthetic communication-trials dataset and explicitly marked DATA_LIMITED;
see ai/training/train.py for the exact real-row count found at training time.
"""

from __future__ import annotations

from sklearn.ensemble import HistGradientBoostingClassifier

from ai.features.feature_builder import CASE_CATEGORICAL_FEATURES, CASE_NUMERIC_FEATURES, FEATURE_VERSION
from ai.models.base import ModelRegistry

MODEL_NAME = "message_response"
NUMERIC_FEATURES = CASE_NUMERIC_FEATURES + ["prior_communications_24h"]
CATEGORICAL_FEATURES = CASE_CATEGORICAL_FEATURES + ["channel", "message_type"]


def build_estimator():
    return HistGradientBoostingClassifier(max_depth=5, max_iter=150, random_state=42)


def predict_one(features: dict, *, channel: str, message_type: str, prior_communications_24h: int = 0) -> dict | None:
    import pandas as pd

    model, metadata = ModelRegistry.load_model(MODEL_NAME)
    if model is None or metadata is None or metadata.feature_version != FEATURE_VERSION:
        return None

    row = {**features, "channel": channel, "message_type": message_type,
           "prior_communications_24h": prior_communications_24h}
    df = pd.DataFrame([row])
    proba = model.predict_proba(df)[0]
    classes = list(model.classes_)
    p = float(proba[classes.index(True)]) if True in classes else float(proba.max())
    return {
        "model_name": MODEL_NAME,
        "model_version": metadata.version,
        "status": metadata.status,   # expected "DATA_LIMITED" — surface this to callers
        "response_probability": round(p, 4),
    }
