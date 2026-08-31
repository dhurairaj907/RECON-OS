"""
RECON OS — Phase 6, Model 1: Payment Failure Diagnosis  (advisory only)

Multiclass classifier over RECON's REAL `FailureCategory` enum (schemas/
intelligence.py) — never an invented label set. Uses only text-derived
keyword features + payment_method + amount (see
ai/features/feature_builder.py:build_diagnosis_features) — never the
category itself, which is the prediction target.

This is advisory context alongside the existing deterministic diagnosis
engine (services/intelligence/ai_diagnosis.py) — it does NOT replace it. The
deterministic engine (optionally Gemini-assisted) remains the diagnosis of
record on `CaseIntelligence`; this model's output is attached separately as
`ml_predictions_json.diagnosis` for comparison/context only.
"""

from __future__ import annotations

from sklearn.ensemble import HistGradientBoostingClassifier

from ai.features.feature_builder import DIAGNOSIS_CATEGORICAL_FEATURES, DIAGNOSIS_NUMERIC_FEATURES, FEATURE_VERSION
from ai.models.base import ModelRegistry, TabularModel

MODEL_NAME = "diagnosis"
NUMERIC_FEATURES = DIAGNOSIS_NUMERIC_FEATURES
CATEGORICAL_FEATURES = DIAGNOSIS_CATEGORICAL_FEATURES


def build_estimator():
    return HistGradientBoostingClassifier(max_depth=6, max_iter=150, random_state=42)


def predict_one(features: dict) -> dict | None:
    import pandas as pd

    model, metadata = ModelRegistry.load_model(MODEL_NAME)
    if model is None or metadata is None:
        return None
    if metadata.feature_version != FEATURE_VERSION:
        return None   # stale artifact — refuse to serve a mismatched feature contract

    df = pd.DataFrame([features])
    proba = model.predict_proba(df)[0]
    classes = model.classes_
    top_idx = int(proba.argmax())
    return {
        "model_name": MODEL_NAME,
        "model_version": metadata.version,
        "status": metadata.status,
        "failure_category": classes[top_idx],
        "confidence": round(float(proba[top_idx]), 4),
        "class_probabilities": {c: round(float(p), 4) for c, p in zip(classes, proba)},
    }
