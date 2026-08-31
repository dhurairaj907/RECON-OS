"""
RECON OS — Policies Router  (Phase 4: PROVE)

    GET /api/v1/policies    read-only description of the live Policy Engine

Every threshold below is read directly from `config.settings` — the exact
values services/intelligence/policy_engine.py enforces — never a hardcoded
copy that could drift from the real engine. This is deliberately read-only:
there is no second, independent validation path that would let an edited
threshold be trusted without also re-verifying it against the engine's own
rule logic, so exposing an editor here would risk a config that LOOKS
enforced but silently isn't. See schemas/policy.py.
"""

from fastapi import APIRouter, Depends

from auth import AuthContext, get_auth_context
from config import settings
from schemas.policy import PolicyConfig, PolicyOverview, PolicyRuleInfo

router = APIRouter(tags=["Policies"])


@router.get("/policies", response_model=PolicyOverview)
def get_policy_overview(ctx: AuthContext = Depends(get_auth_context)):
    max_attempts = int(settings.POLICY_MAX_RECOVERY_ATTEMPTS)
    contact_window = int(settings.POLICY_CONTACT_WINDOW_HOURS)
    max_contacts = int(settings.POLICY_MAX_CONTACTS_PER_WINDOW)
    auto_limit = float(settings.POLICY_AUTO_APPROVAL_AMOUNT_LIMIT)

    rules = [
        PolicyRuleInfo(
            rule_id="RULE_MAX_ATTEMPTS",
            name="Maximum recovery attempts",
            condition=f"A recovery case has already been actioned {max_attempts} or more times.",
            decision="REJECTED — hard stop, not overridable by human approval.",
            action_restriction="No further recovery action is proposable or executable for this case.",
        ),
        PolicyRuleInfo(
            rule_id="RULE_CONTACT_LIMIT",
            name="Customer contact limit",
            condition=(f"The customer has already been contacted (a Payment Link created) "
                      f"{max_contacts} or more time(s) in the last {contact_window} hours, and "
                      f"the recommended action would contact them again."),
            decision="NEEDS_APPROVAL — a human must confirm contacting the customer again is appropriate.",
            action_restriction="Automatic execution is blocked until approved.",
        ),
        PolicyRuleInfo(
            rule_id="RULE_AUTO_APPROVAL_AMOUNT",
            name="Automatic approval amount ceiling",
            condition=f"Classification only — amount at risk compared against ₹{auto_limit:,.2f}.",
            decision="Informational — feeds RULE_HIGH_VALUE_APPROVAL below.",
            action_restriction="None on its own.",
        ),
        PolicyRuleInfo(
            rule_id="RULE_HIGH_VALUE_APPROVAL",
            name="High-value human approval",
            condition=f"Amount at risk exceeds ₹{auto_limit:,.2f}.",
            decision="NEEDS_APPROVAL — a human must approve before execution.",
            action_restriction="Automatic execution is blocked until approved.",
        ),
        PolicyRuleInfo(
            rule_id="RULE_FRAUD_NO_AUTO_RETRY",
            name="Risk / fraud automatic-recovery block",
            condition="The diagnosed failure category is RISK_BLOCK (suspected fraud).",
            decision="REJECTED — hard stop, not overridable by human approval.",
            action_restriction="No automated retry or contact; routed to manual fraud investigation.",
        ),
        PolicyRuleInfo(
            rule_id="RULE_PAYMENT_STATE_VERIFIED",
            name="Payment state verification",
            condition="The underlying payment is not in a known state (\"failed\") at execution time.",
            decision="REJECTED — hard stop.",
            action_restriction="No retry or Payment Link action until the payment state is verified.",
        ),
        PolicyRuleInfo(
            rule_id="RULE_ALLOWED_STRATEGY",
            name="Allowed strategy",
            condition="The recommended strategy is outside RECON's approved action set.",
            decision="REJECTED — hard stop.",
            action_restriction="Only RETRY_NOW / RETRY_DELAYED / SEND_PAYMENT_LINK / CUSTOMER_OUTREACH / "
                               "MANUAL_REVIEW / NO_ACTION may ever reach execution.",
        ),
    ]

    return PolicyOverview(
        config=PolicyConfig(
            max_recovery_attempts=max_attempts,
            contact_window_hours=contact_window,
            max_contacts_per_window=max_contacts,
            auto_approval_amount_limit=auto_limit,
        ),
        rules=rules,
        editable=False,
        note=(
            "Read-only by design: these thresholds are enforced by a single deterministic "
            "Policy Engine (services/intelligence/policy_engine.py) with no LLM involvement. "
            "An editor here would need its own re-validation against that engine's actual rule "
            "logic to avoid a config that looks enforced but isn't — out of scope for this phase. "
            "Change POLICY_* values in the backend environment and restart to adjust them."
        ),
    )
