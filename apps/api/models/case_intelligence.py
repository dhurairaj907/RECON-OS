"""
RECON OS — Case Intelligence Model  (Phase 2: THINK)

Additive persistence for the deterministic intelligence pipeline. Does NOT alter
the Phase 1 `recovery_cases` schema. One row per analysis run; the latest row
(highest `version`) is the current intelligence for a case.

Structured sections are stored as JSON; a handful of scalar columns are
duplicated out for cheap indexing / dashboard aggregation.
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import backref, relationship
from sqlalchemy.sql import func

from database import Base

UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class CaseIntelligence(Base):
    __tablename__ = "case_intelligence"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)

    recovery_case_id = Column(
        UUID_TYPE, ForeignKey("recovery_cases.id"), nullable=False, index=True
    )
    merchant_id = Column(UUID_TYPE, ForeignKey("merchants.id"), nullable=False)

    # Lifecycle: POLICY_APPROVED | NEEDS_APPROVAL | POLICY_REJECTED | FAILED
    status = Column(String(30), nullable=False, default="ANALYZED", index=True)
    # Diagnosis source: "DETERMINISTIC" | "GEMINI"
    provider = Column(String(30), nullable=False, default="DETERMINISTIC")
    # Model / engine version, e.g. "gemini-2.0-flash" or "deterministic-1.0"
    provider_version = Column(String(60), nullable=True)
    # Overall intelligence-pipeline version, e.g. "2.5"
    intelligence_version = Column(String(20), nullable=True)
    version = Column(Integer, nullable=False, default=1)

    # Structured sections
    context_json = Column(JSON_TYPE, nullable=True)
    diagnosis_json = Column(JSON_TYPE, nullable=True)
    prediction_json = Column(JSON_TYPE, nullable=True)
    strategy_json = Column(JSON_TYPE, nullable=True)
    # Phase 10 — intent-aware recovery evidence (see services/intelligence/intent.py)
    intent_json = Column(JSON_TYPE, nullable=True)
    policy_json = Column(JSON_TYPE, nullable=True)

    error_message = Column(Text, nullable=True)

    # Phase 6 — structured ML model predictions (advisory context only; never
    # overwrites diagnosis/prediction/strategy/policy, which stay authoritative
    # and deterministic). None when models aren't trained/available yet.
    ml_predictions_json = Column(JSON_TYPE, nullable=True)

    # Indexed / denormalised scalars for fast filtering & aggregation
    failure_category = Column(String(30), nullable=True, index=True)
    recovery_probability = Column(Numeric(5, 4), nullable=True, index=True)
    prediction_band = Column(String(10), nullable=True)
    recommended_action = Column(String(30), nullable=True, index=True)
    # Phase 10
    intent_classification = Column(String(30), nullable=True, index=True)
    intent_confidence = Column(Numeric(5, 4), nullable=True)
    policy_verdict = Column(String(20), nullable=True, index=True)
    requires_human = Column(Boolean, nullable=False, default=False)
    risk_level = Column(String(10), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    recovery_case = relationship(
        "RecoveryCase",
        backref=backref(
            "intelligence_records",
            lazy="dynamic",
            order_by="desc(CaseIntelligence.version)",
        ),
    )

    __table_args__ = (
        Index("ix_case_intel_case_version", "recovery_case_id", "version"),
        Index("ix_case_intel_merchant_verdict", "merchant_id", "policy_verdict"),
    )

    def __repr__(self):
        return (
            f"<CaseIntelligence case={self.recovery_case_id} v{self.version} "
            f"{self.status} {self.policy_verdict}>"
        )
