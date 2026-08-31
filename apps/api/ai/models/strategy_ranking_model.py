"""
RECON OS — Phase 6, Model 6: Recovery Strategy Ranking  (advisory only)

Trained on (case features + candidate strategy) -> counterfactual
`strategy_recovered`. At inference, every candidate strategy is scored and
ranked by predicted probability — candidates come EXCLUSIVELY from RECON's
real `StrategyAction` enum (schemas/intelligence.py); this model cannot
invent or recommend an action RECON has no way to execute.

This is a RECOMMENDATION ONLY. The deterministic Policy Engine
(services/intelligence/policy_engine.py) remains the sole authority on what
may actually execute — nothing here is wired to bypass it.
"""

from __future__ import annotations

from typing import Optional

from sklearn.ensemble import HistGradientBoostingClassifier

from ai.features.feature_builder import CASE_CATEGORICAL_FEATURES, CASE_NUMERIC_FEATURES, FEATURE_VERSION
from ai.models.base import ModelRegistry
from schemas.intelligence import StrategyAction

MODEL_NAME = "strategy_ranking"
NUMERIC_FEATURES = CASE_NUMERIC_FEATURES
CATEGORICAL_FEATURES = CASE_CATEGORICAL_FEATURES + ["strategy"]
ALL_STRATEGIES = [s.value for s in StrategyAction]


def build_estimator():
    return HistGradientBoostingClassifier(max_depth=6, max_iter=200, random_state=42)


def rank_strategies(features: dict, candidate_strategies: Optional[list[str]] = None) -> dict | None:
    import pandas as pd

    model, metadata = ModelRegistry.load_model(MODEL_NAME)
    if model is None or metadata is None or metadata.feature_version != FEATURE_VERSION:
        return None

    candidates = candidate_strategies or ALL_STRATEGIES
    df = pd.DataFrame([{**features, "strategy": s} for s in candidates])
    proba = model.predict_proba(df)
    classes = list(model.classes_)
    idx_true = classes.index(True) if True in classes else int(proba.mean(axis=0).argmax())
    scores = proba[:, idx_true]

    ranking = sorted(
        ({"strategy": s, "score": round(float(sc), 4)} for s, sc in zip(candidates, scores)),
        key=lambda r: -r["score"],
    )
    return {
        "model_name": MODEL_NAME,
        "model_version": metadata.version,
        "status": metadata.status,
        "ranking": ranking,
    }
