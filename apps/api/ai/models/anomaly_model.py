"""
RECON OS — Phase 6, Model 5: Anomaly Detection  (advisory only)

Unsupervised IsolationForest over the same case numeric features every other
model uses. Flags unusual payment/recovery patterns for operator attention —
it does NOT and cannot block, reject, or alter any financial action; only
the existing Policy Engine has that authority (RULE_FRAUD_NO_AUTO_RETRY etc.
already handles hard fraud blocks deterministically and is unchanged).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ai.features.feature_builder import CASE_NUMERIC_FEATURES, FEATURE_VERSION
from ai.models.base import ARTIFACT_ROOT, ModelMetadata

MODEL_NAME = "anomaly"
NUMERIC_FEATURES = CASE_NUMERIC_FEATURES


class AnomalyModel:
    def __init__(self, contamination: float = 0.03, random_state: int = 42):
        self.estimator = IsolationForest(
            n_estimators=200, contamination=contamination, random_state=random_state
        )
        self._score_min: float = 0.0
        self._score_max: float = 1.0

    def fit(self, df: pd.DataFrame) -> "AnomalyModel":
        X = df[NUMERIC_FEATURES].fillna(0.0)
        self.estimator.fit(X)
        raw = -self.estimator.score_samples(X)   # higher = more anomalous
        self._score_min, self._score_max = float(raw.min()), float(raw.max())
        return self

    def _normalize(self, raw: np.ndarray) -> np.ndarray:
        span = max(self._score_max - self._score_min, 1e-9)
        return np.clip((raw - self._score_min) / span, 0.0, 1.0)

    def score(self, df: pd.DataFrame) -> np.ndarray:
        X = df[NUMERIC_FEATURES].fillna(0.0)
        raw = -self.estimator.score_samples(X)
        return self._normalize(raw)

    def predict_is_anomaly(self, df: pd.DataFrame) -> np.ndarray:
        X = df[NUMERIC_FEATURES].fillna(0.0)
        return self.estimator.predict(X) == -1   # sklearn: -1 anomaly, 1 normal

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"estimator": self.estimator, "score_min": self._score_min, "score_max": self._score_max},
            path / "model.joblib",
        )

    @classmethod
    def load(cls, path: Path) -> "AnomalyModel":
        blob = joblib.load(path / "model.joblib")
        obj = cls.__new__(cls)
        obj.estimator = blob["estimator"]
        obj._score_min = blob["score_min"]
        obj._score_max = blob["score_max"]
        return obj


def _artifact_dir(version: str) -> Path:
    return ARTIFACT_ROOT / MODEL_NAME / version


def load_latest() -> tuple[Optional[AnomalyModel], Optional[ModelMetadata]]:
    model_dir = ARTIFACT_ROOT / MODEL_NAME
    if not model_dir.exists():
        return None, None
    versions = sorted(p.name for p in model_dir.iterdir() if p.is_dir())
    if not versions:
        return None, None
    version = versions[-1]
    path = _artifact_dir(version)
    if not (path / "model.joblib").exists():
        return None, None
    metadata = ModelMetadata(**json.loads((path / "metadata.json").read_text()))
    return AnomalyModel.load(path), metadata
