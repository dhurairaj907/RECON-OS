"""
RECON OS — Phase 6: AI Model Status / Predictions Router  (advisory only)

    GET /api/v1/ai/models                                  registry status for every trained model
    GET /api/v1/recovery-cases/{case_id}/ai-predictions     the ML predictions attached to a case

Both endpoints are read-only and metadata-level: they expose what a model
IS (name/version/algorithm/metrics/status) and what it PREDICTED for one
case, never a training dataset or a raw model artifact file. Same
authentication + organization isolation as every other router — a case's
predictions are only visible to a caller whose organization owns that case.

Nothing here can trigger training, execute an action, or send a
communication — this router only reads what ai/training and the
intelligence orchestrator have already written.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai.models.base import ModelRegistry
from auth import AuthContext, get_auth_context
from database import get_db, get_org_merchant
from models.case_intelligence import CaseIntelligence
from models.recovery_case import RecoveryCase
from schemas.ai import CasePredictionsResponse, ModelStatusItem, ModelStatusResponse

router = APIRouter(tags=["AI Intelligence"])


@router.get("/ai/models", response_model=ModelStatusResponse)
def get_model_status(ctx: AuthContext = Depends(get_auth_context)):
    """Registry status for every trained model — any authenticated member of
    an organization may view this (read-only, no sensitive data)."""
    return ModelStatusResponse(models=[ModelStatusItem(**m) for m in ModelRegistry.list_models()])


@router.get(
    "/recovery-cases/{case_id}/ai-predictions",
    response_model=CasePredictionsResponse,
)
def get_case_ai_predictions(
    case_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """The advisory ML predictions attached to a case's latest intelligence
    run. Never influences and is never influenced by the deterministic
    Policy Engine verdict — see services/intelligence/orchestrator.py."""
    merchant = get_org_merchant(db, ctx.organization)

    query = db.query(RecoveryCase).filter(RecoveryCase.merchant_id == merchant.id)
    try:
        case = query.filter(
            (RecoveryCase.id == UUID(case_id)) | (RecoveryCase.case_number == case_id)
        ).first()
    except ValueError:
        case = query.filter(RecoveryCase.case_number == case_id).first()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recovery case not found")

    ci = (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id == case.id)
        .order_by(CaseIntelligence.version.desc())
        .first()
    )
    if ci is None:
        return CasePredictionsResponse(
            case_id=str(case.id), case_number=case.case_number, analyzed=False,
            note="This case has not been analyzed yet.",
        )

    preds = ci.ml_predictions_json
    return CasePredictionsResponse(
        case_id=str(case.id),
        case_number=case.case_number,
        analyzed=True,
        generated_at=(preds or {}).get("generated_at"),
        predictions=preds,
        note=None if preds else "No ML predictions were available for this analysis run.",
    )
