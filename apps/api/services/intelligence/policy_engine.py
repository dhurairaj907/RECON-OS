"""
RECON OS — Phase 2: Deterministic Policy Engine  (SAFETY-CRITICAL)

Authoritative, deterministic validation of a strategy recommendation. Contains
NO LLM logic. An LLM can never override, skip, or soften this component.

Verdicts: APPROVED | NEEDS_APPROVAL | REJECTED

Phase 2 stops here. The Policy Engine does NOT execute anything — Phase 3 (ACT)
will consume `allowed_actions` and route NEEDS_APPROVAL through a human gate.

Thresholds are operator-configurable via `config.Settings` (POLICY_*), not
hardcoded across the codebase.
"""

import logging
from decimal import Decimal

from config import settings
from schemas.intelligence import (
    CaseContext,
    DiagnosisResult,
    PolicyResult,
    PolicyRuleResult,
    PolicyVerdict,
    PredictionResult,
    RiskLevel,
    StrategyAction,
    StrategyResult,
)
from services.intelligence import weights

logger = logging.getLogger("recon.services.intelligence.policy")

# Actions that constitute an outbound customer contact (contact-rate limited)
_CONTACT_ACTIONS = {StrategyAction.SEND_PAYMENT_LINK, StrategyAction.CUSTOMER_OUTREACH}
# Actions that move/attempt money (never allowed for risk-blocked payments)
_RETRY_ACTIONS = {StrategyAction.RETRY_NOW, StrategyAction.RETRY_DELAYED}
# Payment states we consider "known and safe to reason about"
_KNOWN_PAYMENT_STATES = {"failed"}
# Every action the strategy layer is permitted to emit
_ALLOWED_STRATEGY_ACTIONS = set(StrategyAction)


def evaluate_policy(
    ctx: CaseContext,
    diagnosis: DiagnosisResult,
    prediction: PredictionResult,  # noqa: ARG001 - reserved for future rules
    strategy: StrategyResult,
) -> PolicyResult:
    max_attempts = int(settings.POLICY_MAX_RECOVERY_ATTEMPTS)
    contact_window = int(settings.POLICY_CONTACT_WINDOW_HOURS)
    max_contacts = int(settings.POLICY_MAX_CONTACTS_PER_WINDOW)
    auto_limit = Decimal(str(settings.POLICY_AUTO_APPROVAL_AMOUNT_LIMIT))

    category = diagnosis.failure_category.value
    action = strategy.action
    amount = Decimal(ctx.amount)

    rules: list[PolicyRuleResult] = []
    violated: list[str] = []
    reject = False
    needs_approval = False

    def rule(rule_id, name, description, passed, detail):
        rules.append(PolicyRuleResult(
            rule_id=rule_id, name=name, description=description,
            passed=passed, detail=detail,
        ))
        if not passed:
            violated.append(rule_id)

    # RULE 1 — Maximum recovery attempts
    r1_pass = ctx.attempt_count < max_attempts
    rule(
        "RULE_MAX_ATTEMPTS", "Maximum recovery attempts",
        f"A recovery case may be actioned at most {max_attempts} times.",
        r1_pass,
        f"attempt_count={ctx.attempt_count}, limit={max_attempts}"
        + ("" if r1_pass else " — exhausted"),
    )
    if not r1_pass:
        reject = True

    # RULE 2 — Customer contact limit (24h window)
    is_contact = action in _CONTACT_ACTIONS
    r2_pass = (not is_contact) or (ctx.customer_contacts_last_24h < max_contacts)
    rule(
        "RULE_CONTACT_LIMIT", "Customer contact limit",
        f"At most {max_contacts} outbound customer contact per {contact_window}h window.",
        r2_pass,
        (f"action={action.value}, contacts_last_{contact_window}h="
         f"{ctx.customer_contacts_last_24h}, limit={max_contacts}")
        + ("" if r2_pass else " — would exceed contact limit"),
    )
    if not r2_pass:
        needs_approval = True

    # RULE 3 — Amount eligible for automatic approval (classification, never a
    # hard violation on its own; the human-approval requirement is RULE 4).
    within_ceiling = amount <= auto_limit
    rule(
        "RULE_AUTO_APPROVAL_AMOUNT", "Automatic approval amount ceiling",
        f"Amounts ≤ {ctx.currency} {auto_limit} are eligible for automatic approval.",
        True,
        (f"amount={ctx.currency} {amount} — eligible for automatic approval"
         if within_ceiling
         else f"amount={ctx.currency} {amount} exceeds the {ctx.currency} {auto_limit} "
              f"ceiling — not eligible for automatic approval (see RULE_HIGH_VALUE_APPROVAL)"),
    )

    # RULE 4 — High-value requires explicit human approval
    r4_pass = amount <= auto_limit
    rule(
        "RULE_HIGH_VALUE_APPROVAL", "High-value human approval",
        f"Amounts > {ctx.currency} {auto_limit} require explicit human approval.",
        r4_pass,
        ("within auto ceiling" if r4_pass
         else f"amount={ctx.currency} {amount} exceeds ceiling — human approval required"),
    )
    if not r4_pass:
        needs_approval = True

    # RULE 5 — Risk / fraud block cannot be auto-recovered
    is_risk = category == "RISK_BLOCK"
    r5_pass = not is_risk
    rule(
        "RULE_FRAUD_NO_AUTO_RETRY", "Risk / fraud automatic-recovery block",
        "Risk/fraud-blocked payments cannot be automatically retried or contacted; "
        "they require manual investigation.",
        r5_pass,
        "no risk block detected" if r5_pass
        else f"failure_category=RISK_BLOCK with recommended action {action.value} — automated recovery not permitted",
    )
    if not r5_pass:
        reject = True

    # RULE 6 — Payment state must be known/verified before action
    state = (ctx.payment_status or "").lower().strip()
    action_needs_state = action in (_RETRY_ACTIONS | {StrategyAction.SEND_PAYMENT_LINK})
    r6_pass = (not action_needs_state) or (state in _KNOWN_PAYMENT_STATES)
    rule(
        "RULE_PAYMENT_STATE_VERIFIED", "Payment state verification",
        "The payment must be in a known state (failed) before any retry/link action.",
        r6_pass,
        f"payment_status='{state or 'unknown'}', action={action.value}"
        + ("" if r6_pass else " — state must be verified first"),
    )
    if not r6_pass:
        reject = True

    # RULE 7 — Only allowed strategies may pass
    r7_pass = action in _ALLOWED_STRATEGY_ACTIONS
    rule(
        "RULE_ALLOWED_STRATEGY", "Allowed strategy",
        "Only strategies in the approved action set may pass the policy engine.",
        r7_pass,
        f"action={action.value}"
        + (" is allowed" if r7_pass else " is NOT in the allowed action set"),
    )
    if not r7_pass:
        reject = True

    # --- Verdict aggregation -------------------------------------------------
    if reject:
        verdict = PolicyVerdict.REJECTED
    elif action == StrategyAction.MANUAL_REVIEW or needs_approval:
        verdict = PolicyVerdict.NEEDS_APPROVAL
    else:
        verdict = PolicyVerdict.APPROVED

    # --- Risk level --------------------------------------------------------
    if is_risk:
        risk = RiskLevel.HIGH
    elif amount > weights.AMOUNT_BAND_MEDIUM_MAX:
        risk = RiskLevel.HIGH
    elif amount > auto_limit or category in ("BANK_DECLINE", "INSUFFICIENT_FUNDS"):
        risk = RiskLevel.MEDIUM
    else:
        risk = RiskLevel.LOW

    requires_human = verdict in (PolicyVerdict.NEEDS_APPROVAL, PolicyVerdict.REJECTED)

    if verdict == PolicyVerdict.APPROVED:
        allowed_actions = [action] if action != StrategyAction.NO_ACTION else []
    else:
        allowed_actions = []

    reason = _reason(verdict, violated, rules, action, amount, ctx.currency, auto_limit, is_risk)

    return PolicyResult(
        verdict=verdict,
        risk_level=risk,
        requires_human=requires_human,
        reason=reason,
        evaluated_rules=rules,
        violated_rules=violated,
        allowed_actions=allowed_actions,
        provider="DETERMINISTIC",
    )


def _reason(verdict, violated, rules, action, amount, currency, auto_limit, is_risk) -> str:
    if verdict == PolicyVerdict.REJECTED:
        if is_risk:
            return ("Rejected: risk/fraud-blocked payment. Automated recovery is not "
                    "permitted — route to manual fraud investigation.")
        failed = [r.name for r in rules if not r.passed]
        return f"Rejected: policy rule(s) failed — {', '.join(failed)}."
    if verdict == PolicyVerdict.NEEDS_APPROVAL:
        if action == StrategyAction.MANUAL_REVIEW:
            return "Needs approval: recommended action is manual review by design."
        if amount > auto_limit:
            return (f"Needs approval: amount {currency} {amount} exceeds the automatic "
                    f"approval ceiling of {currency} {auto_limit}.")
        return "Needs approval: one or more policy checks require a human decision."
    return (f"Approved: recommended action '{action.value}' passed all policy checks "
            f"and the amount is within the automatic approval ceiling.")
