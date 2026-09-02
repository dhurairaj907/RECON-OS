"""
RECON OS — Phase 6: Shared Model Wrapper + Registry  (SAFETY: advisory only)

One `TabularModel` wrapper (a scikit-learn `ColumnTransformer` preprocessor +
estimator `Pipeline`) is reused by every classification/regression model in
this package — this is what keeps 6+ models from turning into 6+ bespoke
training scripts. Anomaly detection (unsupervised) has its own thin wrapper
in ai/models/anomaly_model.py since IsolationForest's interface differs.

Nothing in this module (or anything that imports it) can reach the Razorpay
adapter, the Action Engine, or a communication provider — it has no
knowledge of those modules at all. A prediction is a plain Python
value/dict; turning it into money movement or a customer message is the
sole responsibility of the existing Policy Engine / Action Engine /
Communication service, unchanged by Phase 6.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ARTIFACT_ROOT = Path(__file__).resolve().parent.parent / "artifacts"

STATUS_READY = "READY"                # trained on adequate synthetic data, real-data volume insufficient
STATUS_DATA_LIMITED = "DATA_LIMITED"  # even the synthetic label signal is thin; treat cautiously
STATUS_EXPERIMENTAL = "EXPERIMENTAL"  # pipeline works but no real-world validation yet

# `status` above answers "is this model adequately trained/validated on its
# OWN development distribution (synthetic or real)?" — a SEPARATE, ORTHOGONAL
# question is "has this model's real-world discriminative power actually
# been checked against real outcomes?". A model can be STATUS_READY (good
# synthetic training) while still being REAL_VALIDATION_NONE/INSUFFICIENT —
# conflating the two would hide exactly the honesty gap this field exists to
# surface (e.g. recovery_probability: solid synthetic training, but recon_dev.db
# currently has zero real negative-outcome examples to validate against).
REAL_VALIDATION_NONE = "NONE"                  # zero real samples used in evaluation at all
REAL_VALIDATION_INSUFFICIENT = "INSUFFICIENT"  # real samples exist but too few/imbalanced to validate
REAL_VALIDATION_PARTIAL = "PARTIAL"            # a real held-out evaluation exists but is still small/narrow
REAL_VALIDATION_FULL = "FULL"                  # validated on a real, sufficiently sized, balanced held-out set


@dataclass
class ModelMetadata:
    model_name: str
    version: str                   # MODEL_VERSION — bumped on algorithm/training-code changes
    training_timestamp: str
    dataset_type: str              # "SYNTHETIC" | "REAL" | "MIXED"
    feature_version: str
    algorithm: str
    training_sample_count: int
    validation_sample_count: int
    metrics: dict = field(default_factory=dict)
    status: str = STATUS_READY
    label_classes: Optional[list] = None
    real_sample_count: int = 0
    notes: str = ""
    # DATASET_VERSION — bumped only when the dataset generation/extraction
    # logic itself changes (synthetic assumption tables, real-data query
    # shape), independent of the model's own algorithm/training-code version.
    dataset_version: str = "1.0"
    # See REAL_VALIDATION_* constants above — orthogonal to `status`.
    real_world_validation: str = REAL_VALIDATION_NONE

    def to_dict(self) -> dict:
        return asdict(self)


class TabularModel:
    """Wraps a scikit-learn estimator behind a fixed preprocessing pipeline:
    median-impute + passthrough numerics, most-frequent-impute + one-hot
    categoricals. `task` is "classification" or "regression"."""

    def __init__(self, estimator, numeric_features: list[str], categorical_features: list[str], task: str):
        self.numeric_features = numeric_features
        self.categorical_features = categorical_features
        self.task = task
        pre = ColumnTransformer(
            transformers=[
                ("num", SimpleImputer(strategy="median"), numeric_features),
                ("cat", Pipeline([
                    ("impute", SimpleImputer(strategy="most_frequent")),
                    ("onehot", OneHotEncoder(handle_unknown="ignore")),
                ]), categorical_features),
            ]
        )
        self.pipeline = Pipeline([("pre", pre), ("model", estimator)])
        self.classes_: Optional[list] = None

    def _X(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = self.numeric_features + self.categorical_features
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required feature columns: {missing}")
        return df[cols]

    def fit(self, df: pd.DataFrame, y) -> "TabularModel":
        self.pipeline.fit(self._X(df), y)
        if self.task == "classification":
            self.classes_ = list(self.pipeline.named_steps["model"].classes_)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.pipeline.predict(self._X(df))

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        if self.task != "classification":
            raise ValueError("predict_proba is only valid for classification models")
        return self.pipeline.predict_proba(self._X(df))

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"pipeline": self.pipeline, "numeric_features": self.numeric_features,
             "categorical_features": self.categorical_features, "task": self.task,
             "classes_": self.classes_},
            path / "model.joblib",
        )

    @classmethod
    def load(cls, path: Path) -> "TabularModel":
        blob = joblib.load(path / "model.joblib")
        obj = cls.__new__(cls)
        obj.pipeline = blob["pipeline"]
        obj.numeric_features = blob["numeric_features"]
        obj.categorical_features = blob["categorical_features"]
        obj.task = blob["task"]
        obj.classes_ = blob["classes_"]
        return obj


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelRegistry:
    """Filesystem-backed registry: apps/api/ai/artifacts/<model_name>/<version>/
    {model.joblib, metadata.json}. Gitignored — rebuild via `python -m
    ai.training.train`. Loading is read-only and never trains anything."""

    @staticmethod
    def _model_dir(model_name: str) -> Path:
        return ARTIFACT_ROOT / model_name

    @staticmethod
    def path_for(model_name: str, version: str) -> Path:
        return ModelRegistry._model_dir(model_name) / version

    @staticmethod
    def latest_version(model_name: str) -> Optional[str]:
        d = ModelRegistry._model_dir(model_name)
        if not d.exists():
            return None
        versions = sorted(
            (p.name for p in d.iterdir() if p.is_dir() and (p / "metadata.json").exists()),
            key=lambda v: v.lstrip("v").zfill(6),
        )
        return versions[-1] if versions else None

    @staticmethod
    def save(model_name: str, version: str, model: TabularModel, metadata: ModelMetadata) -> Path:
        path = ModelRegistry.path_for(model_name, version)
        model.save(path)
        (path / "metadata.json").write_text(json.dumps(metadata.to_dict(), indent=2))
        return path

    @staticmethod
    def load_metadata(model_name: str, version: Optional[str] = None) -> Optional[ModelMetadata]:
        version = version or ModelRegistry.latest_version(model_name)
        if version is None:
            return None
        path = ModelRegistry.path_for(model_name, version)
        meta_path = path / "metadata.json"
        if not meta_path.exists():
            return None
        return ModelMetadata(**json.loads(meta_path.read_text()))

    @staticmethod
    def load_model(model_name: str, version: Optional[str] = None) -> tuple[Optional[TabularModel], Optional[ModelMetadata]]:
        version = version or ModelRegistry.latest_version(model_name)
        if version is None:
            return None, None
        path = ModelRegistry.path_for(model_name, version)
        if not (path / "model.joblib").exists():
            return None, None
        metadata = ModelRegistry.load_metadata(model_name, version)
        return TabularModel.load(path), metadata

    @staticmethod
    def list_models() -> list[dict]:
        if not ARTIFACT_ROOT.exists():
            return []
        out = []
        for model_dir in sorted(ARTIFACT_ROOT.iterdir()):
            if not model_dir.is_dir():
                continue
            latest = ModelRegistry.latest_version(model_dir.name)
            versions = sorted(p.name for p in model_dir.iterdir() if p.is_dir())
            meta = ModelRegistry.load_metadata(model_dir.name, latest) if latest else None
            out.append({
                "model_name": model_dir.name,
                "versions": versions,
                "latest_version": latest,
                "metadata": meta.to_dict() if meta else None,
            })
        return out
