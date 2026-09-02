"""
RECON OS — Phase 6: AI model status/prediction schemas.

Read-only, metadata-level views over ai.models.base.ModelRegistry. Never
exposes a training dataset or a raw model artifact — only the metadata that
was written alongside it at training time (algorithm, sample counts,
metrics, status). See routers/ai.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ModelMetadataOut(BaseModel):
    model_name: str
    version: str
    training_timestamp: str
    dataset_type: str
    feature_version: str
    algorithm: str
    training_sample_count: int
    validation_sample_count: int
    metrics: dict[str, Any] = {}
    status: str
    label_classes: Optional[list] = None
    real_sample_count: int = 0
    notes: str = ""
    dataset_version: str = "1.0"
    # NONE | INSUFFICIENT | PARTIAL | FULL — orthogonal to `status`; see
    # ai/models/base.py's REAL_VALIDATION_* constants.
    real_world_validation: str = "NONE"


class ModelStatusItem(BaseModel):
    model_name: str
    versions: list[str]
    latest_version: Optional[str]
    metadata: Optional[ModelMetadataOut]


class ModelStatusResponse(BaseModel):
    models: list[ModelStatusItem]


class CasePredictionsResponse(BaseModel):
    case_id: str
    case_number: str
    analyzed: bool
    generated_at: Optional[datetime] = None
    predictions: Optional[dict[str, Any]] = None
    note: Optional[str] = None
