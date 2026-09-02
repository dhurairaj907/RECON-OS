"""
RECON OS — Phase 2 (THINK) Intelligence Package

Deterministic, explainable, testable revenue-recovery intelligence.

Pipeline (orchestrated by `orchestrator.run_intelligence`):

    build_case_context -> diagnose -> predict -> recommend_strategy
        -> evaluate_intent (Phase 10)  -> evaluate_policy

Hard architectural boundary: nothing in this package calls Razorpay, moves
money, executes an action, sends a communication, or bypasses the Policy
Engine. The Policy Engine is deterministic and authoritative — Phase 10's
intent evaluation (services/intelligence/intent.py, ai_intent.py) only ever
feeds it additional structured evidence via two new rules
(RULE_INTENT_UNWILLING / RULE_INTENT_EVIDENCE); it can never itself approve,
reject, or execute anything.
"""

from services.intelligence.context_builder import build_case_context
from services.intelligence.diagnosis import diagnose
from services.intelligence.intent import evaluate_intent
from services.intelligence.prediction import predict
from services.intelligence.strategy import recommend_strategy
from services.intelligence.policy_engine import evaluate_policy

__all__ = [
    "build_case_context",
    "diagnose",
    "evaluate_intent",
    "predict",
    "recommend_strategy",
    "evaluate_policy",
]
