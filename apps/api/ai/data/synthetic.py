"""
RECON OS — Phase 6: Synthetic Training Dataset  (DEVELOPMENT / VALIDATION ONLY)

`recon_dev.db` currently holds ~38 recovery cases — far too few to train any
model with statistical validity. Per the Phase 6 directive, this module
generates a deterministic, documented, clearly-labeled SYNTHETIC dataset for
development/validation. It is NEVER represented as real customer data and
NEVER used to report production performance — every row is tagged
`dataset_type="SYNTHETIC"`, and every model trained on it records that in its
metadata (see ai/models/base.py, ai/training/train.py).

Generation is a fixed-seed, explicit, documented statistical process — not a
black box: category base-recovery-rates, method/attempt/amount effects, and
strategy/channel multipliers are named constants below, not hidden inside
`numpy` calls. Reproducible: the same seed always produces the same dataset.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ai.data import DATASET_TYPE_SYNTHETIC

SEED = 42

FAILURE_CATEGORIES = [
    "AUTH_TIMEOUT", "INSUFFICIENT_FUNDS", "BANK_DECLINE",
    "TECHNICAL_GATEWAY", "RISK_BLOCK", "USER_ABANDONED",
]
# Roughly matches the relative frequency of failure reasons in real payment
# processing (funds/decline/timeout dominate; fraud blocks are rare).
CATEGORY_PROBS = [0.20, 0.24, 0.18, 0.16, 0.06, 0.16]

PAYMENT_METHODS = ["upi", "card", "netbanking", "wallet"]
METHOD_PROBS = [0.45, 0.30, 0.15, 0.10]

STRATEGIES = [
    "RETRY_NOW", "RETRY_DELAYED", "SEND_PAYMENT_LINK",
    "CUSTOMER_OUTREACH", "MANUAL_REVIEW", "NO_ACTION",
]
CHANNELS = ["EMAIL", "SMS", "WHATSAPP"]
MESSAGE_TYPES = ["PAYMENT_FAILED", "PAYMENT_RECOVERY", "PAYMENT_LINK_CREATED", "RECOVERY_REMINDER"]

# Representative failure text per category, built from the SAME keyword lists
# services/intelligence/weights.py already uses for the deterministic
# diagnosis engine — this is what lets the diagnosis model's text-derived
# keyword features carry real signal instead of noise.
CATEGORY_SAMPLE_TEXT = {
    "AUTH_TIMEOUT": [
        "Authentication timed out before OTP entry", "3DS session expired, no response",
        "Authorization did not complete in time",
    ],
    "INSUFFICIENT_FUNDS": [
        "Insufficient funds in account", "Transaction exceeds available balance",
        "Payment declined: low balance",
    ],
    "BANK_DECLINE": [
        "Card declined by issuer, do not honour", "Bank refused the transaction",
        "Issuer declined: invalid card",
    ],
    "TECHNICAL_GATEWAY": [
        "Gateway server error during processing", "Upstream connection error, processing failed",
        "Internal server error at payment gateway",
    ],
    "RISK_BLOCK": [
        "Blocked by risk engine, suspicious transaction", "Flagged for fraud review",
        "Transaction blocked, velocity check failed",
    ],
    "USER_ABANDONED": [
        "Customer abandoned checkout before completing", "User cancelled the payment",
        "Customer closed the page mid-transaction",
    ],
}

# Documented, explicit assumption tables (NOT hidden inside distributions) —
# a richer, noisier ground truth than the hand-tuned deterministic scorecard
# in weights.py, so the ML models have real (if synthetic) signal to learn
# beyond simply re-deriving the existing rules.
CATEGORY_BASE_RECOVERY = {
    "AUTH_TIMEOUT": 0.70, "TECHNICAL_GATEWAY": 0.62, "USER_ABANDONED": 0.50,
    "INSUFFICIENT_FUNDS": 0.38, "BANK_DECLINE": 0.32, "RISK_BLOCK": 0.05,
}
METHOD_BONUS = {"upi": 0.05, "wallet": 0.02, "card": 0.0, "netbanking": -0.04}
STRATEGY_MULTIPLIER = {
    "RETRY_NOW": 1.00, "RETRY_DELAYED": 1.05, "SEND_PAYMENT_LINK": 1.18,
    "CUSTOMER_OUTREACH": 1.10, "MANUAL_REVIEW": 0.85, "NO_ACTION": 0.25,
}
# Fraud-flagged cases: only manual review is a genuinely effective/safe
# strategy — mirrors the real Policy Engine's RULE_FRAUD_NO_AUTO_RETRY intent.
RISK_BLOCK_STRATEGY_OVERRIDE = {
    "RETRY_NOW": 0.10, "RETRY_DELAYED": 0.10, "SEND_PAYMENT_LINK": 0.15,
    "CUSTOMER_OUTREACH": 0.20, "MANUAL_REVIEW": 1.8, "NO_ACTION": 0.5,
}
CHANNEL_AMOUNT_BAND_BONUS = {   # WhatsApp/SMS favored for smaller/personal amounts, email for larger/formal
    "MICRO": {"WHATSAPP": 0.12, "SMS": 0.08, "EMAIL": -0.05},
    "SMALL": {"WHATSAPP": 0.08, "SMS": 0.04, "EMAIL": 0.0},
    "MEDIUM": {"WHATSAPP": 0.0, "SMS": -0.02, "EMAIL": 0.06},
    "LARGE": {"WHATSAPP": -0.08, "SMS": -0.06, "EMAIL": 0.10},
}
FATIGUE_PENALTY_PER_PRIOR_CONTACT = 0.06   # each prior contact in 24h lowers response odds


def _amount_band(amount: float) -> str:
    if amount <= 5000:
        return "MICRO"
    if amount <= 15000:
        return "SMALL"
    if amount <= 50000:
        return "MEDIUM"
    return "LARGE"


def _clip(p: float, lo: float = 0.02, hi: float = 0.98) -> float:
    return max(lo, min(hi, p))


def generate_case_dataset(n: int = 3000, seed: int = SEED) -> pd.DataFrame:
    """
    One row per synthetic recovery case, with a documented generative process
    for the `recovered` and `recovery_hours` targets, plus injected outliers
    for anomaly-detection evaluation (`is_anomaly_injected`).
    """
    rng = np.random.default_rng(seed)

    n_customers = max(1, n // 4)
    customer_quality = rng.beta(2.0, 2.0, size=n_customers)          # latent "how reliable a payer" per customer
    customer_tenure = rng.integers(0, 15, size=n_customers)          # prior case count pool

    customer_id = rng.integers(0, n_customers, size=n)
    failure_category = rng.choice(FAILURE_CATEGORIES, size=n, p=CATEGORY_PROBS)
    payment_method = rng.choice(PAYMENT_METHODS, size=n, p=METHOD_PROBS)
    amount = np.round(rng.lognormal(mean=8.6, sigma=1.0, size=n), 2)
    amount = np.clip(amount, 100, 500_000)
    attempt_count = rng.choice([0, 1, 2, 3], size=n, p=[0.55, 0.27, 0.13, 0.05])
    hours_since_failure = np.round(rng.exponential(scale=18.0, size=n), 2)

    quality = customer_quality[customer_id]
    success_noise = rng.normal(0, 0.05, size=n)
    customer_success_rate = np.clip(quality + success_noise, 0.0, 1.0)
    customer_lifetime_amount = np.round(quality * rng.uniform(20_000, 300_000, size=n), 2)
    prev_cases = np.clip(customer_tenure[customer_id] + rng.integers(-1, 2, size=n), 0, None)
    prev_resolved = np.round(prev_cases * customer_success_rate).astype(int)
    prev_attempts = prev_cases + rng.integers(0, 2, size=n)
    contacts_24h = rng.choice([0, 1, 2], size=n, p=[0.82, 0.14, 0.04])
    has_history = (prev_cases + attempt_count) >= 2

    amount_band = np.array([_amount_band(a) for a in amount])
    failure_text = np.array([
        rng.choice(CATEGORY_SAMPLE_TEXT[cat]) for cat in failure_category
    ])

    base_p = np.array([CATEGORY_BASE_RECOVERY[c] for c in failure_category])
    method_bonus = np.array([METHOD_BONUS[m] for m in payment_method])
    attempt_penalty = np.where(attempt_count >= 3, -0.22, -0.06 * attempt_count)
    amount_penalty = np.where(amount_band == "LARGE", -0.08, np.where(amount_band == "MEDIUM", -0.03, 0.0))
    history_bonus = np.where(has_history, 0.04, 0.0)
    noise = rng.normal(0, 0.08, size=n)

    p_recover = base_p + 0.25 * (customer_success_rate - 0.5) + method_bonus + attempt_penalty + amount_penalty + history_bonus + noise
    p_recover = np.array([_clip(p) for p in p_recover])
    recovered = rng.random(n) < p_recover

    # Recovery time: faster for higher-quality customers / smaller amounts.
    time_scale = 6.0 + 24.0 * (1 - customer_success_rate) + np.where(amount_band == "LARGE", 12.0, 0.0)
    recovery_hours = np.where(recovered, np.round(rng.gamma(shape=2.0, scale=time_scale / 2.0), 2), np.nan)

    # Injected outliers for anomaly-detection evaluation only (~2%) — a
    # SYNTHETIC stress-test label, never a claim about real fraud/anomalies.
    is_anomaly_injected = rng.random(n) < 0.02
    outlier_mult = rng.uniform(15, 40, size=n)
    amount = np.where(is_anomaly_injected, np.round(amount * outlier_mult, 2), amount)
    attempt_count = np.where(is_anomaly_injected, rng.integers(4, 8, size=n), attempt_count)

    df = pd.DataFrame({
        "case_idx": np.arange(n),
        "customer_id": customer_id,
        "amount": amount,
        "amount_band": np.array([_amount_band(a) for a in amount]),
        "payment_method": payment_method,
        "failure_category": failure_category,
        "failure_reason": failure_text,
        "failure_description": failure_text,
        "failure_code": np.full(n, ""),
        "attempt_count": attempt_count,
        "max_attempts": np.full(n, 3),
        "hours_since_failure": hours_since_failure,
        "customer_successful_payments": np.round(customer_success_rate * (prev_cases + 1) * 3).astype(int),
        "customer_failed_payments": np.round((1 - customer_success_rate) * (prev_cases + 1) * 3).astype(int),
        "customer_lifetime_amount": customer_lifetime_amount,
        "customer_success_rate": customer_success_rate,
        "customer_has_history": has_history,
        "previous_recovery_cases": prev_cases,
        "previous_resolved_cases": prev_resolved,
        "previous_recovery_attempts": prev_attempts,
        "customer_contacts_last_24h": contacts_24h,
        "recovered": recovered,
        "recovery_hours": recovery_hours,
        "is_anomaly_injected": is_anomaly_injected,
        "dataset_type": DATASET_TYPE_SYNTHETIC,
    })
    return df


def generate_strategy_trials(case_df: pd.DataFrame, seed: int = SEED + 1, strategies_per_case: int = 3) -> pd.DataFrame:
    """
    Long table: (case features, candidate strategy) -> counterfactual
    `strategy_recovered`. Trains Model 6 (strategy ranking) as a binary
    classifier over (features + strategy); at inference every candidate
    strategy is scored and ranked by predicted probability.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for _, row in case_df.iterrows():
        chosen = rng.choice(STRATEGIES, size=strategies_per_case, replace=False)
        base_p = CATEGORY_BASE_RECOVERY[row["failure_category"]] + 0.25 * (row["customer_success_rate"] - 0.5)
        for strategy in chosen:
            mult = (RISK_BLOCK_STRATEGY_OVERRIDE if row["failure_category"] == "RISK_BLOCK" else STRATEGY_MULTIPLIER)[strategy]
            p = _clip(base_p * mult + rng.normal(0, 0.05))
            rows.append({**row.to_dict(), "strategy": strategy, "strategy_recovered": rng.random() < p})
    out = pd.DataFrame(rows)
    out["dataset_type"] = DATASET_TYPE_SYNTHETIC
    return out


def generate_communication_trials(case_df: pd.DataFrame, seed: int = SEED + 2, rows_per_case: int = 2) -> pd.DataFrame:
    """
    Long table: (case features, channel, message_type, prior_communications
    in the last 24h) -> `responded`. Backs BOTH Model 8 (channel ranking) and
    Model 9 (message response) — same underlying engagement data, two
    distinct trained models answering two distinct questions (which channel
    to prefer, vs. how likely a specific already-chosen send is to work).
    """
    rng = np.random.default_rng(seed)
    rows = []
    for _, row in case_df.iterrows():
        for _ in range(rows_per_case):
            channel = rng.choice(CHANNELS)
            message_type = rng.choice(MESSAGE_TYPES)
            prior = rng.choice([0, 1, 2, 3], p=[0.55, 0.25, 0.13, 0.07])
            base_p = CATEGORY_BASE_RECOVERY[row["failure_category"]] + 0.20 * (row["customer_success_rate"] - 0.5)
            band_bonus = CHANNEL_AMOUNT_BAND_BONUS[row["amount_band"]][channel]
            fatigue = -FATIGUE_PENALTY_PER_PRIOR_CONTACT * prior
            p = _clip(base_p + band_bonus + fatigue + rng.normal(0, 0.06))
            rows.append({
                **row.to_dict(), "channel": channel, "message_type": message_type,
                "prior_communications_24h": prior, "responded": rng.random() < p,
            })
    out = pd.DataFrame(rows)
    out["dataset_type"] = DATASET_TYPE_SYNTHETIC
    return out


def generate_customer_dataset(case_df: pd.DataFrame) -> pd.DataFrame:
    """
    Customer-grain aggregation for Model 4 (customer recovery/churn): for
    each synthetic customer with >= 2 cases, the LATEST case's `recovered`
    outcome is the label; every earlier case feeds the aggregate features —
    strictly no leakage from the labeled case into its own features.
    """
    rows = []
    for customer_id, group in case_df.groupby("customer_id"):
        if len(group) < 2:
            continue
        group_sorted = group.sort_values("case_idx")
        history, latest = group_sorted.iloc[:-1], group_sorted.iloc[-1]
        rows.append({
            "customer_id": customer_id,
            "total_prior_cases": len(history),
            "prior_recovered_count": int(history["recovered"].sum()),
            "prior_recovery_rate": float(history["recovered"].mean()),
            "avg_amount": float(history["amount"].mean()),
            "customer_success_rate": float(latest["customer_success_rate"]),
            "customer_lifetime_amount": float(latest["customer_lifetime_amount"]),
            "customer_has_history": bool(latest["customer_has_history"]),
            "amount_band": latest["amount_band"],
            "payment_method": latest["payment_method"],
            "failure_category": latest["failure_category"],
            "next_case_recovered": bool(latest["recovered"]),
            "dataset_type": DATASET_TYPE_SYNTHETIC,
        })
    return pd.DataFrame(rows)
