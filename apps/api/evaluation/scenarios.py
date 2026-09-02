"""
RECON OS — Phase 4 (PROVE): Evaluation scenarios.

Each scenario drives the REAL pipeline (process_inbound_event ->
run_intelligence -> get_or_create_action -> execute_action -> approval /
UNKNOWN verification / reconcile) against an isolated in-memory database and
a deterministic fake Razorpay double. Nothing here re-implements product
logic or hardcodes an expected number that isn't independently derived from
config/policy — see runner.py for how results are aggregated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from config import settings
from evaluation.fake_razorpay import fake_razorpay
from evaluation.harness import (
    analyze,
    create_case,
    isolated_db,
    payment_captured_payload,
    payment_failed_payload,
    propose,
    set_payment_status,
)
from models.case_intelligence import CaseIntelligence
from models.recovery_action import RecoveryAction
from services.actions.approval import approve_action, reject_action
from services.actions.common import ui_state
from services.actions.executor import execute_action
from services.actions.proposal import get_or_create_action
from services.actions.unknown import verify_unknown_action
from services.communications.service import send_communication
from services.event_processor import process_inbound_event


@dataclass
class ScenarioResult:
    scenario_id: int
    name: str
    tags: list[str]
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(ok for _, ok, _ in self.checks)


class _Recorder:
    def __init__(self, scenario_id: int, name: str, tags: list[str]):
        self.result = ScenarioResult(scenario_id=scenario_id, name=name, tags=tags)

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.result.checks.append((name, bool(condition), detail))


def _run(scenario_id: int, name: str, tags: list[str], body) -> ScenarioResult:
    r = _Recorder(scenario_id, name, tags)
    try:
        body(r)
    except Exception as e:  # a scenario blowing up is itself a finding, not a crash
        r.result.error = f"{type(e).__name__}: {e}"
    return r.result


def _latest_ci(db, case) -> CaseIntelligence | None:
    return (
        db.query(CaseIntelligence)
        .filter(CaseIntelligence.recovery_case_id == case.id)
        .order_by(CaseIntelligence.version.desc())
        .first()
    )


def _payment_link_paid_payload(*, event_id, plink_id, ref, amount, amount_paid=None, status="paid"):
    amount_paid = amount if amount_paid is None else amount_paid
    return {
        "entity": "event", "event": "payment_link.paid", "contains": ["payment_link", "payment"],
        "id": event_id,
        "payload": {
            "payment_link": {"entity": {
                "id": plink_id, "reference_id": ref, "amount": amount,
                "amount_paid": amount_paid, "currency": "INR", "status": status,
                "created_at": 1700000200}},
            "payment": {"entity": {
                "id": "pay_" + event_id, "amount": amount_paid, "currency": "INR",
                "status": "captured", "method": "upi", "created_at": 1700000200}},
        },
        "created_at": 1700000200,
    }


# ===========================================================================
# 1. Normal payment failure
# ===========================================================================
def scenario_01(r: _Recorder):
    with isolated_db() as (db, merchant):
        case = create_case(db, merchant, payment_failed_payload())
        r.check("case_created", case is not None)
        r.check("status_detected", case.status == "DETECTED", case.status)
        r.check("amount_matches", Decimal(case.amount_at_risk) == Decimal("4999.00"))


# ===========================================================================
# 2. Automatically recoverable payment
# ===========================================================================
def scenario_02(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        r.check("proposable", action is not None)
        result = execute_action(db, action.id)
        r.check("executed", result.status == "EXECUTED", result.status)
        r.check("outcome_pending_not_recovered", result.outcome == "PENDING")
        r.check("payment_link_created", bool(result.provider_action_id))
        r.check("one_razorpay_call", len(rzp.calls) == 1)


# ===========================================================================
# 3. Low recovery probability (relative to a strong-history customer)
# ===========================================================================
def scenario_03(r: _Recorder):
    with isolated_db() as (db, merchant):
        for i in range(4):
            create_case(db, merchant, payment_failed_payload(
                event_id=f"evt_weak_{i}", payment_id=f"pay_weak_{i}", customer_id="cust_weak"))
        weak_case = create_case(db, merchant, payment_failed_payload(
            event_id="evt_weak_final", payment_id="pay_weak_final", customer_id="cust_weak"))
        analyze(db, weak_case)
        weak_ci = _latest_ci(db, weak_case)

        for i in range(4):
            process_inbound_event(db=db, raw_payload=payment_captured_payload(
                event_id=f"evt_strong_cap_{i}", payment_id=f"pay_strong_cap_{i}",
                amount_paise=499900, customer_id="cust_strong"), merchant_id=merchant.id)
        strong_case = create_case(db, merchant, payment_failed_payload(
            event_id="evt_strong_final", payment_id="pay_strong_final", customer_id="cust_strong"))
        analyze(db, strong_case)
        strong_ci = _latest_ci(db, strong_case)

        r.check("both_analyzed", weak_ci is not None and strong_ci is not None)
        if weak_ci and strong_ci:
            r.check(
                "weak_history_lowers_probability",
                float(weak_ci.recovery_probability) < float(strong_ci.recovery_probability),
                f"weak={weak_ci.recovery_probability} strong={strong_ci.recovery_probability}",
            )


# ===========================================================================
# 4. High-value payment -> NEEDS_APPROVAL, HIGH risk
# ===========================================================================
def scenario_04(r: _Recorder):
    with isolated_db() as (db, merchant):
        case = create_case(db, merchant, payment_failed_payload(
            amount_paise=7500000, method="netbanking",
            error_description="Corporate netbanking approval limit exceeded"))
        analyze(db, case)
        ci = _latest_ci(db, case)
        r.check("needs_approval", ci.policy_verdict == "NEEDS_APPROVAL", ci.policy_verdict)
        r.check("high_risk", ci.risk_level == "HIGH", ci.risk_level)


# ===========================================================================
# 5. NEEDS_APPROVAL blocks execution
# ===========================================================================
def scenario_05(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload(
            amount_paise=1499900, method="card", error_code="GATEWAY_ERROR",
            error_description="Transaction declined: insufficient funds / limit exceeded"))
        analyze(db, case)
        action = propose(db, case)
        result = execute_action(db, action.id)
        r.check("blocked", result.status == "BLOCKED", result.status)
        r.check("needs_approval_reason", result.blocked_reason == "NEEDS_APPROVAL", result.blocked_reason)
        r.check("no_razorpay_call", len(rzp.calls) == 0)


# ===========================================================================
# 6. Human approval -> executes
# ===========================================================================
def scenario_06(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload(
            amount_paise=1499900, method="card", error_code="GATEWAY_ERROR",
            error_description="Transaction declined: insufficient funds / limit exceeded"))
        analyze(db, case)
        action = propose(db, case)
        execute_action(db, action.id)
        approved = approve_action(db, action.id, decided_by="eval-operator")
        r.check("executed_after_approval", approved.status == "EXECUTED", approved.status)
        r.check("human_decision_recorded", approved.human_decision == "APPROVED")
        r.check("payment_link_created", bool(approved.provider_action_id))
        r.check("one_razorpay_call", len(rzp.calls) == 1)


# ===========================================================================
# 7. Human rejection -> terminal, never executes
# ===========================================================================
def scenario_07(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload(
            amount_paise=1499900, method="card", error_code="GATEWAY_ERROR",
            error_description="Transaction declined: insufficient funds / limit exceeded"))
        analyze(db, case)
        action = propose(db, case)
        execute_action(db, action.id)
        rejected = reject_action(db, action.id, decided_by="eval-operator", reason="suspicious")
        r.check("blocked", rejected.status == "BLOCKED", rejected.status)
        r.check("human_rejected_reason", rejected.blocked_reason == "HUMAN_REJECTED")
        r.check("never_executed", len(rzp.calls) == 0)


# ===========================================================================
# 8. Policy rejection (fresh re-evaluation, not the stored verdict)
# ===========================================================================
def scenario_08(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        r.check("stored_verdict_approved", action.policy_verdict == "APPROVED", action.policy_verdict)
        set_payment_status(db, case, "unknown")
        result = execute_action(db, action.id)
        r.check("blocked_on_fresh_reevaluation", result.status == "BLOCKED", result.status)
        r.check("policy_rejected", result.blocked_reason == "POLICY_REJECTED", result.blocked_reason)
        r.check("no_razorpay_call", len(rzp.calls) == 0)


# ===========================================================================
# 9. Maximum recovery attempts exhausted -> not proposable
# ===========================================================================
def scenario_09(r: _Recorder):
    with isolated_db() as (db, merchant):
        case = create_case(db, merchant, payment_failed_payload())
        case.attempt_count = int(settings.POLICY_MAX_RECOVERY_ATTEMPTS)
        db.commit()
        analyze(db, case)
        action, proposal = get_or_create_action(db, case)
        r.check("not_proposable", action is None, str(action))
        r.check(
            "strategy_not_eligible",
            proposal.not_proposable_reason == "STRATEGY_NOT_ELIGIBLE",
            proposal.not_proposable_reason,
        )


# ===========================================================================
# 10. Duplicate webhook does not double-count
# ===========================================================================
def scenario_10(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay():
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        executed = execute_action(db, action.id)

        payload = _payment_link_paid_payload(
            event_id="evt_dup_webhook", plink_id=executed.provider_action_id,
            ref=executed.reference_id, amount=499900)
        process_inbound_event(db=db, raw_payload=payload, merchant_id=merchant.id)
        db.refresh(case)
        first_recovered = Decimal(case.amount_recovered)

        process_inbound_event(db=db, raw_payload=payload, merchant_id=merchant.id)   # same event id
        db.refresh(case)
        second_recovered = Decimal(case.amount_recovered)

        r.check("recovered_once", first_recovered == Decimal("4999.00"), str(first_recovered))
        r.check("not_double_counted", second_recovered == first_recovered, str(second_recovered))


# ===========================================================================
# 11. Duplicate action proposal is idempotent
# ===========================================================================
def scenario_11(r: _Recorder):
    with isolated_db() as (db, merchant):
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        a1, _ = get_or_create_action(db, case)
        a2, _ = get_or_create_action(db, case)
        r.check("same_action_returned", a1.id == a2.id)
        count = db.query(RecoveryAction).filter_by(recovery_case_id=case.id).count()
        r.check("only_one_row", count == 1, str(count))


# ===========================================================================
# 12. Definitive provider failure -> FAILED, safely retryable
# ===========================================================================
def scenario_12(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        rzp.status = 500
        rzp.body = {"error": {"description": "server blew up"}}
        result = execute_action(db, action.id)
        r.check("failed", result.status == "FAILED", result.status)
        r.check("definitive_error_code", result.error_code == "RAZORPAY_API_ERROR", result.error_code)

        rzp.status = 200
        rzp.body = None
        retry = execute_action(db, action.id)
        r.check("safe_retry_succeeds", retry.status == "EXECUTED", retry.status)


# ===========================================================================
# 13. Provider timeout -> UNKNOWN, not FAILED
# ===========================================================================
def scenario_13(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        rzp.mode = "timeout"
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        result = execute_action(db, action.id)
        r.check("not_failed", result.status != "FAILED", result.status)
        r.check("outcome_unknown", result.outcome == "UNKNOWN", result.outcome)
        r.check("error_code_timeout", result.error_code == "RAZORPAY_TIMEOUT")


# ===========================================================================
# 14. UNKNOWN action renders as a distinct UI state
# ===========================================================================
def scenario_14(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        rzp.mode = "timeout"
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        result = execute_action(db, action.id)
        r.check("ui_state_unknown", ui_state(result) == "UNKNOWN", ui_state(result))
        r.check("ui_state_not_failed", ui_state(result) != "FAILED")


# ===========================================================================
# 15. UNKNOWN -> verified SUCCESS (found on Razorpay, no duplicate)
# ===========================================================================
def scenario_15(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        rzp.mode = "timeout"
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        execute_action(db, action.id)

        rzp.mode = "success"
        rzp.search_items = [{
            "id": "plink_EVAL_FOUND", "short_url": "https://rzp.io/i/EVALFOUND",
            "status": "created", "reference_id": action.reference_id,
            "amount": action.amount_paise, "amount_paid": 0, "currency": "INR", "payments": [],
        }]
        resolved = verify_unknown_action(db, action.id)
        r.check("resolved_executed", resolved.status == "EXECUTED", resolved.status)
        r.check("resolved_pending_outcome", resolved.outcome == "PENDING")
        r.check("no_duplicate_created", len(rzp.calls) == 1)


# ===========================================================================
# 16. UNKNOWN -> verified FAILED (confirmed never created)
# ===========================================================================
def scenario_16(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        rzp.mode = "timeout"
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        execute_action(db, action.id)

        rzp.mode = "success"
        rzp.search_items = []
        resolved = verify_unknown_action(db, action.id)
        r.check("resolved_failed", resolved.status == "FAILED", resolved.status)
        r.check("verified_not_created", resolved.error_code == "RAZORPAY_TIMEOUT_VERIFIED_NOT_CREATED")


# ===========================================================================
# 17. UNKNOWN remains UNKNOWN when verification is inconclusive
# ===========================================================================
def scenario_17(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        rzp.mode = "timeout"
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        execute_action(db, action.id)

        resolved = verify_unknown_action(db, action.id)   # still in timeout mode
        r.check("still_unknown", resolved.outcome == "UNKNOWN", resolved.outcome)
        r.check("never_guessed", resolved.status not in ("FAILED",))


# ===========================================================================
# 18. Safe retry after a verified failure
# ===========================================================================
def scenario_18(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        rzp.mode = "timeout"
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        execute_action(db, action.id)

        rzp.mode = "success"
        rzp.search_items = []
        resolved = verify_unknown_action(db, action.id)   # -> FAILED, verified
        retry = execute_action(db, resolved.id)
        r.check("retry_executes", retry.status == "EXECUTED", retry.status)
        r.check("two_real_attempts", len(rzp.calls) == 2)


# ===========================================================================
# 19. Unsafe retry prevention (blind retry while still UNKNOWN)
# ===========================================================================
def scenario_19(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        rzp.mode = "timeout"
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        execute_action(db, action.id)

        rzp.mode = "success"   # would succeed now, but must never be blindly tried
        again = execute_action(db, action.id)
        r.check("still_unknown_no_blind_retry", again.outcome == "UNKNOWN", again.outcome)
        r.check("no_second_razorpay_call", len(rzp.calls) == 1, str(len(rzp.calls)))


# ===========================================================================
# 20. Idempotency of an already-executed action
# ===========================================================================
def scenario_20(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        r1 = execute_action(db, action.id)
        r2 = execute_action(db, action.id)
        r3 = execute_action(db, action.id)
        r.check("same_provider_id", r1.provider_action_id == r2.provider_action_id == r3.provider_action_id)
        r.check("exactly_one_call", len(rzp.calls) == 1, str(len(rzp.calls)))


# ===========================================================================
# 21. Invalid action (zero amount) is blocked, never sent to Razorpay
# ===========================================================================
def scenario_21(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        action.amount = Decimal("0.00")
        db.commit()
        result = execute_action(db, action.id)
        r.check("blocked", result.status == "BLOCKED", result.status)
        r.check("invalid_amount", result.blocked_reason == "INVALID_AMOUNT")
        r.check("no_razorpay_call", len(rzp.calls) == 0)


# ===========================================================================
# 22. Stale approval is not honoured once state changes
# ===========================================================================
def scenario_22(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload(
            amount_paise=1499900, method="card", error_code="GATEWAY_ERROR",
            error_description="Transaction declined: insufficient funds / limit exceeded"))
        analyze(db, case)
        action = propose(db, case)
        execute_action(db, action.id)   # -> BLOCKED / NEEDS_APPROVAL

        action.human_decision = "APPROVED"   # a decision made under now-stale conditions
        db.commit()
        set_payment_status(db, case, "unknown")   # state changed since the decision

        result = execute_action(db, action.id)
        r.check("blocked_despite_stale_approval", result.status == "BLOCKED", result.status)
        r.check("policy_rejected_wins", result.blocked_reason == "POLICY_REJECTED", result.blocked_reason)
        r.check("stale_decision_cleared", result.human_decision is None)
        r.check("no_razorpay_call", len(rzp.calls) == 0)


# ===========================================================================
# 23. Policy re-evaluated fresh at execution, not trusted from analysis time
# ===========================================================================
def scenario_23(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay() as rzp:
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        r.check("stored_verdict_was_approved", action.policy_verdict == "APPROVED")

        case.attempt_count = int(settings.POLICY_MAX_RECOVERY_ATTEMPTS)
        db.commit()

        result = execute_action(db, action.id)
        r.check("blocked_on_fresh_state", result.status == "BLOCKED", result.status)
        r.check("no_razorpay_call", len(rzp.calls) == 0)


# ===========================================================================
# 24. Customer contact limit blocks a second contact within the window
# ===========================================================================
def scenario_24(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay():
        case1 = create_case(db, merchant, payment_failed_payload(
            event_id="evt_contact_1", payment_id="pay_contact_1", customer_id="cust_contact"))
        analyze(db, case1)
        action1 = propose(db, case1)
        execute_action(db, action1.id)   # a real "contact" — sets executed_at

        case2 = create_case(db, merchant, payment_failed_payload(
            event_id="evt_contact_2", payment_id="pay_contact_2", customer_id="cust_contact",
            error_reason="user_cancelled",
            error_description="Customer abandoned the payment before completing it"))
        analyze(db, case2)
        ci2 = _latest_ci(db, case2)
        violated = (ci2.policy_json or {}).get("violated_rules", [])
        r.check("contact_limit_rule_fires", "RULE_CONTACT_LIMIT" in violated, str(violated))
        r.check("second_contact_needs_approval", ci2.policy_verdict in ("NEEDS_APPROVAL", "REJECTED"), ci2.policy_verdict)


# ===========================================================================
# 25. Full successful recovery, revenue actually recovered
# ===========================================================================
def scenario_25(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay():
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        executed = execute_action(db, action.id)
        r.check("executed", executed.status == "EXECUTED")

        payload = _payment_link_paid_payload(
            event_id="evt_full_recovery", plink_id=executed.provider_action_id,
            ref=executed.reference_id, amount=499900)
        process_inbound_event(db=db, raw_payload=payload, merchant_id=merchant.id)

        db.refresh(case)
        a = db.query(RecoveryAction).filter_by(id=action.id).first()
        r.check("outcome_recovered", a.outcome == "RECOVERED", a.outcome)
        r.check("case_resolved", case.status == "RESOLVED", case.status)
        r.check("revenue_recovered", Decimal(case.amount_recovered) == Decimal("4999.00"))


# ===========================================================================
# 26. Recovery communication — real send path, approved template, honest
#     SENT status (a demo must never claim DELIVERED without a provider
#     webhook confirmation — see services/communications/service.py)
# ===========================================================================
def scenario_26(r: _Recorder):
    with isolated_db() as (db, merchant), fake_razorpay():
        case = create_case(db, merchant, payment_failed_payload())
        analyze(db, case)
        action = propose(db, case)
        executed = execute_action(db, action.id)
        r.check("executed", executed.status == "EXECUTED", executed.status)

        comm = send_communication(
            db, merchant_id=merchant.id, case=case, channel="EMAIL",
            message_type="PAYMENT_LINK_CREATED", decided_by="evaluation",
        )
        r.check("communication_sent", comm.status == "SENT", comm.status)
        r.check("uses_approved_template", bool(comm.subject) and bool(comm.body))
        r.check("never_fabricates_delivered", comm.status != "DELIVERED", comm.status)
        r.check("provider_recorded", comm.provider == "FAKE_EMAIL", comm.provider)


SCENARIOS = [
    (1, "Normal payment failure", ["diagnosis"], scenario_01),
    (2, "Automatically recoverable payment", ["recovery_outcome", "action_safety"], scenario_02),
    (3, "Low recovery probability", ["prediction"], scenario_03),
    (4, "High-value payment", ["policy_safety", "strategy"], scenario_04),
    (5, "NEEDS_APPROVAL", ["policy_safety", "approval_safety"], scenario_05),
    (6, "Human approval", ["approval_safety", "recovery_outcome"], scenario_06),
    (7, "Human rejection", ["approval_safety", "action_safety"], scenario_07),
    (8, "Policy rejection", ["policy_safety", "action_safety"], scenario_08),
    (9, "Maximum recovery attempts", ["strategy", "policy_safety"], scenario_09),
    (10, "Duplicate webhook", ["idempotency", "verification"], scenario_10),
    (11, "Duplicate action", ["idempotency"], scenario_11),
    (12, "Definitive provider failure", ["action_safety"], scenario_12),
    (13, "Provider timeout", ["unknown_safety", "action_safety"], scenario_13),
    (14, "UNKNOWN action", ["unknown_safety"], scenario_14),
    (15, "UNKNOWN -> verified SUCCESS", ["unknown_safety", "verification"], scenario_15),
    (16, "UNKNOWN -> verified FAILED", ["unknown_safety", "verification"], scenario_16),
    (17, "UNKNOWN remains UNKNOWN", ["unknown_safety"], scenario_17),
    (18, "Safe retry after verified failure", ["unknown_safety", "action_safety"], scenario_18),
    (19, "Unsafe retry prevention", ["unknown_safety", "idempotency"], scenario_19),
    (20, "Idempotency", ["idempotency"], scenario_20),
    (21, "Invalid action", ["action_safety"], scenario_21),
    (22, "Stale approval", ["approval_safety", "policy_safety"], scenario_22),
    (23, "Policy change after initial recommendation", ["policy_safety"], scenario_23),
    (24, "Customer contact limit", ["policy_safety"], scenario_24),
    (25, "Successful recovery", ["recovery_outcome", "verification"], scenario_25),
    (26, "Recovery communication", ["communication"], scenario_26),
]


def run_all() -> list[ScenarioResult]:
    return [_run(sid, name, tags, body) for sid, name, tags, body in SCENARIOS]
