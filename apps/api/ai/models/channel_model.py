"""
RECON OS — Phase 6, Model 8: Communication Channel Ranking  (advisory only)

Ranks RECON's REAL supported channels (EMAIL/SMS/WHATSAPP —
schemas/communication.py) for a case's next communication. `message_type`
and `prior_communications_24h` are INPUT features (already known at decision
time), `channel` is the ranked dimension.

This model NEVER sends anything and never sees opt-out/contact-availability
data — that filtering is the caller's responsibility (see
ai/inference/service.py), which removes any channel the customer has opted
out of or has no contact info for BEFORE returning a ranking, and the actual
send always goes through services/communications/service.py's existing
policy-aware, rate-limited, duplicate-prevented path.
"""

from __future__ import annotations

from typing import Optional

from sklearn.ensemble import HistGradientBoostingClassifier

from ai.features.feature_builder import CASE_CATEGORICAL_FEATURES, CASE_NUMERIC_FEATURES, FEATURE_VERSION
from ai.models.base import ModelRegistry

MODEL_NAME = "communication_channel"
NUMERIC_FEATURES = CASE_NUMERIC_FEATURES + ["prior_communications_24h"]
CATEGORICAL_FEATURES = CASE_CATEGORICAL_FEATURES + ["channel", "message_type"]
ALL_CHANNELS = ["EMAIL", "SMS", "WHATSAPP"]


def build_estimator():
    return HistGradientBoostingClassifier(max_depth=6, max_iter=200, random_state=42)


def rank_channels(
    features: dict, *, message_type: str, prior_communications_24h: int = 0,
    candidate_channels: Optional[list[str]] = None,
) -> dict | None:
    import pandas as pd

    model, metadata = ModelRegistry.load_model(MODEL_NAME)
    if model is None or metadata is None or metadata.feature_version != FEATURE_VERSION:
        return None

    candidates = candidate_channels if candidate_channels is not None else ALL_CHANNELS
    if not candidates:
        return {"model_name": MODEL_NAME, "model_version": metadata.version,
                "status": metadata.status, "ranking": []}

    df = pd.DataFrame([
        {**features, "channel": c, "message_type": message_type,
         "prior_communications_24h": prior_communications_24h}
        for c in candidates
    ])
    proba = model.predict_proba(df)
    classes = list(model.classes_)
    idx_true = classes.index(True) if True in classes else int(proba.mean(axis=0).argmax())
    scores = proba[:, idx_true]

    ranking = sorted(
        ({"channel": c, "score": round(float(sc), 4)} for c, sc in zip(candidates, scores)),
        key=lambda r: -r["score"],
    )
    return {
        "model_name": MODEL_NAME,
        "model_version": metadata.version,
        "status": metadata.status,
        "ranking": ranking,
    }
