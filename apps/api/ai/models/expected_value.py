"""
RECON OS — Phase 6, Model 7: Expected Recovery Value  (deterministic calculation)

Not a separately trained model — a calculation layer combining Model 6/8's
per-strategy or per-channel probabilities with the case amount and a
documented, explicit intervention-cost assumption table (no real RECON cost
data exists yet; these are stated estimates, not measured figures).

    expected_recovery_value = probability * amount - estimated_intervention_cost

This answers "which PERMITTED intervention recovers the most money", not
just "which has the highest probability" — exactly the Phase 6 directive.
Purely advisory: it never selects or executes anything. The Policy Engine
still independently determines what is actually permitted; this only adds a
`expected_recovery_value` figure alongside each option already produced by
Models 6/8.
"""

from __future__ import annotations

# Stated assumptions (INR) — RECON has no measured per-channel/strategy cost
# data yet. Reasonable order-of-magnitude estimates only, clearly documented
# rather than hidden inside a computation.
STRATEGY_COST_INR = {
    "RETRY_NOW": 0.0,
    "RETRY_DELAYED": 0.0,
    "SEND_PAYMENT_LINK": 0.0,     # Razorpay payment-link creation has no modeled RECON-side cost
    "CUSTOMER_OUTREACH": 1.0,     # approx. one outbound message
    "MANUAL_REVIEW": 50.0,        # approx. operator time cost
    "NO_ACTION": 0.0,
}
CHANNEL_COST_INR = {"EMAIL": 0.1, "SMS": 0.5, "WHATSAPP": 0.8}


def compute_strategy_expected_values(amount: float, strategy_ranking: list[dict]) -> list[dict]:
    out = []
    for item in strategy_ranking:
        strategy = item["strategy"]
        p = float(item["score"])
        cost = STRATEGY_COST_INR.get(strategy, 0.0)
        out.append({
            "strategy": strategy,
            "recovery_probability": round(p, 4),
            "estimated_cost": cost,
            "expected_recovery_value": round(p * float(amount) - cost, 2),
        })
    return sorted(out, key=lambda r: -r["expected_recovery_value"])


def compute_channel_expected_values(amount: float, channel_ranking: list[dict]) -> list[dict]:
    out = []
    for item in channel_ranking:
        channel = item["channel"]
        p = float(item["score"])
        cost = CHANNEL_COST_INR.get(channel, 0.0)
        out.append({
            "channel": channel,
            "response_probability": round(p, 4),
            "estimated_cost": cost,
            "expected_recovery_value": round(p * float(amount) - cost, 2),
        })
    return sorted(out, key=lambda r: -r["expected_recovery_value"])
