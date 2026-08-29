"""
RECON OS — Phase 2: Intelligence Orchestrator

Deterministic Python control flow that runs the pipeline and persists the
result. The orchestrator decides execution order — an agent never calls another
agent, and an LLM is never asked "what should run next".

    load RecoveryCase
        -> build CaseContext
        -> diagnose
        -> predict
        -> recommend_strategy
        -> evaluate_policy
        -> persist CaseIntelligence (new version)
        -> write AuditLog trail
        -> return CaseIntelligence
"""

import logging

import database
from config import settings
from models.audit_log import AuditLog
from models.case_intelligence import CaseIntelligence
from models.recovery_case import RecoveryCase
from schemas.intelligence import VERDICT_TO_STATUS
from services.intelligence.ai_diagnosis import diagnose_case
from services.intelligence.context_builder import build_case_context
from services.intelligence.policy_engine import evaluate_policy
from services.intelligence.prediction import predict
from services.intelligence.strategy import recommend_strategy
from services.intelligence.weights import INTELLIGENCE_VERSION

logger = logging.getLogger("recon.services.intelligence.orchestrator")


def _audit(db, merchant_id, case_id, actor, action, detail, metadata):
    db.add(AuditLog(
        merchant_id=merchant_id,
        recovery_case_id=case_id,
        actor=actor,
        action=action,
        detail=detail,
        metadata_json=metadata,
    ))


def run_intelligence(db, case_id, *, trigger: str = "manual") -> CaseIntelligence:
    """
    Run the full intelligence pipeline for one recovery case using the provided
    session, and commit. Returns the persisted CaseIntelligence row (which may
    have status FAILED if a component raised).

    This function OWNS its transaction boundary — callers must not wrap it in an
    outer transaction they care about.
    """
    case = db.query(RecoveryCase).filter(RecoveryCase.id == case_id).first()
    if case is None:
        raise ValueError(f"Recovery case {case_id} not found")

    merchant_id = case.merchant_id
    prev = (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id == case.id)
        .order_by(CaseIntelligence.version.desc())
        .first()
    )
    version = (prev.version + 1) if prev else 1
    intelligence_version = settings.INTELLIGENCE_VERSION
    ai_configured = bool(settings.LLM_ENABLED and settings.LLM_PROVIDER)

    # INTELLIGENCE_STARTED is committed immediately so it survives a later failure
    _audit(
        db, merchant_id, case.id, "RECON_ENGINE", "INTELLIGENCE_STARTED",
        f"Intelligence pipeline started for {case.case_number} "
        f"(v{version}, intelligence_version={intelligence_version}, "
        f"ai_configured={ai_configured}, trigger={trigger})",
        {"trigger": trigger, "version": version,
         "intelligence_version": intelligence_version,
         "ai_configured": ai_configured},
    )
    db.commit()

    try:
        ctx = build_case_context(db, case)

        # --- Diagnosis (optional AI assist; prediction/policy stay deterministic) ---
        if ai_configured:
            _audit(
                db, merchant_id, case.id, "DIAGNOSIS_AGENT", "AI_DIAGNOSIS_STARTED",
                f"Attempting AI-assisted diagnosis (provider={settings.LLM_PROVIDER})",
                {"provider": settings.LLM_PROVIDER, "version": version},
            )

        diagnosis, ai_meta = diagnose_case(ctx)

        if ai_meta.used_ai:
            _audit(
                db, merchant_id, case.id, "DIAGNOSIS_AGENT", "AI_DIAGNOSIS_COMPLETED",
                f"AI diagnosis: {diagnosis.failure_category.value} "
                f"(confidence {diagnosis.confidence:.0%}) via {ai_meta.provider} "
                f"{ai_meta.provider_version}",
                {"provider": ai_meta.provider,
                 "provider_version": ai_meta.provider_version,
                 "failure_category": diagnosis.failure_category.value,
                 "confidence": diagnosis.confidence, "status": "completed"},
            )
        elif ai_meta.attempted:
            action = "AI_DIAGNOSIS_FAILED" if ai_meta.error_type == "internal_error" else "AI_DIAGNOSIS_FALLBACK"
            _audit(
                db, merchant_id, case.id, "DIAGNOSIS_AGENT", action,
                f"AI diagnosis unavailable — deterministic fallback used "
                f"({ai_meta.fallback_reason})",
                {"provider": settings.LLM_PROVIDER,
                 "error_type": ai_meta.error_type,
                 "fallback_reason": ai_meta.fallback_reason,
                 "status": "fallback", "version": version},
            )

        _audit(
            db, merchant_id, case.id, "DIAGNOSIS_AGENT", "DIAGNOSIS_COMPLETED",
            f"Diagnosis: {diagnosis.failure_category.value} "
            f"(confidence {diagnosis.confidence:.0%}, source={diagnosis.provider}) "
            f"— {diagnosis.probable_cause}",
            {"failure_category": diagnosis.failure_category.value,
             "confidence": diagnosis.confidence,
             "provider": diagnosis.provider,
             "provider_version": diagnosis.provider_version,
             "evidence": diagnosis.evidence},
        )

        prediction = predict(ctx, diagnosis)
        _audit(
            db, merchant_id, case.id, "PREDICTION_AGENT", "PREDICTION_COMPLETED",
            f"Recovery probability {prediction.recovery_probability:.0%} "
            f"({prediction.band.value}), confidence {prediction.confidence:.0%}",
            {"recovery_probability": prediction.recovery_probability,
             "band": prediction.band.value,
             "base_rate": prediction.base_rate,
             "features": [f.model_dump(mode="json") for f in prediction.features_used]},
        )

        strategy = recommend_strategy(ctx, diagnosis, prediction)
        _audit(
            db, merchant_id, case.id, "STRATEGY_AGENT", "STRATEGY_COMPLETED",
            f"Recommended strategy: {strategy.action.value} "
            f"(confidence {strategy.confidence:.0%}) — {strategy.rationale}",
            {"action": strategy.action.value, "params": strategy.params,
             "confidence": strategy.confidence,
             "alternatives": [a.model_dump(mode="json") for a in strategy.alternatives]},
        )

        policy = evaluate_policy(ctx, diagnosis, prediction, strategy)
        _audit(
            db, merchant_id, case.id, "POLICY_ENGINE", "POLICY_EVALUATED",
            f"Policy verdict: {policy.verdict.value} (risk {policy.risk_level.value}, "
            f"requires_human={policy.requires_human}) — {policy.reason}",
            {"verdict": policy.verdict.value,
             "risk_level": policy.risk_level.value,
             "requires_human": policy.requires_human,
             "violated_rules": policy.violated_rules,
             "evaluated_rules": [r.model_dump(mode="json") for r in policy.evaluated_rules],
             "allowed_actions": [a.value for a in policy.allowed_actions]},
        )

        lifecycle_status = VERDICT_TO_STATUS[policy.verdict.value]

        ci = CaseIntelligence(
            recovery_case_id=case.id,
            merchant_id=merchant_id,
            status=lifecycle_status,
            provider=diagnosis.provider,
            provider_version=diagnosis.provider_version,
            intelligence_version=intelligence_version,
            version=version,
            context_json=ctx.model_dump(mode="json"),
            diagnosis_json=diagnosis.model_dump(mode="json"),
            prediction_json=prediction.model_dump(mode="json"),
            strategy_json=strategy.model_dump(mode="json"),
            policy_json=policy.model_dump(mode="json"),
            failure_category=diagnosis.failure_category.value,
            recovery_probability=prediction.recovery_probability,
            prediction_band=prediction.band.value,
            recommended_action=strategy.action.value,
            policy_verdict=policy.verdict.value,
            requires_human=policy.requires_human,
            risk_level=policy.risk_level.value,
        )
        db.add(ci)
        db.flush()

        _audit(
            db, merchant_id, case.id, "RECON_ENGINE", "INTELLIGENCE_COMPLETED",
            f"Intelligence complete for {case.case_number}: "
            f"diagnosis={diagnosis.failure_category.value} (source={diagnosis.provider}) / "
            f"P(recovery)={prediction.recovery_probability:.0%} ({prediction.band.value}) / "
            f"{strategy.action.value} / policy={policy.verdict.value}",
            {"version": version, "status": lifecycle_status,
             "provider": diagnosis.provider,
             "provider_version": diagnosis.provider_version,
             "intelligence_version": intelligence_version,
             "failure_category": diagnosis.failure_category.value,
             "recovery_probability": prediction.recovery_probability,
             "recommended_action": strategy.action.value,
             "policy_verdict": policy.verdict.value},
        )
        db.commit()
        db.refresh(ci)
        logger.info(
            "Intelligence complete for %s v%s -> %s / %s",
            case.case_number, version, lifecycle_status, policy.verdict.value,
        )
        return ci

    except Exception as e:  # pragma: no cover - defensive
        db.rollback()
        logger.exception("Intelligence pipeline failed for case %s", case_id)
        ci = CaseIntelligence(
            recovery_case_id=case_id,
            merchant_id=merchant_id,
            status="FAILED",
            provider="DETERMINISTIC",
            provider_version=f"deterministic-{INTELLIGENCE_VERSION}",
            intelligence_version=settings.INTELLIGENCE_VERSION,
            version=version,
            error_message=str(e)[:1000],
        )
        db.add(ci)
        try:
            _audit(
                db, merchant_id, case_id, "RECON_ENGINE", "INTELLIGENCE_FAILED",
                f"Intelligence pipeline failed for case {case_id}: {e}",
                {"error": str(e)[:500], "version": version},
            )
            db.commit()
            db.refresh(ci)
        except Exception:
            db.rollback()
        return ci


def run_intelligence_isolated(case_id, *, trigger: str = "pipeline") -> None:
    """
    Fire-and-forget wrapper used by the Phase 1 pipeline hook. Opens its OWN
    database session so it can never interfere with the Phase 1 transaction, and
    never raises — a Phase 2 failure must not fail a webhook or the simulator.
    """
    db = database.SessionLocal()
    try:
        run_intelligence(db, case_id, trigger=trigger)
    except Exception:
        logger.exception(
            "Isolated intelligence run failed for case %s (non-fatal)", case_id
        )
    finally:
        db.close()
