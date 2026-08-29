"""
RECON OS — Phase 2 Intelligence: Centralised, documented tuning constants.

Every number that influences a diagnosis, a recovery-probability score, or a
strategy choice lives here so the model is auditable in one place. The Policy
Engine's *safety* thresholds live in `config.Settings` (operator-configurable),
not here.

Nothing in this module is random or time-seeded. Given the same CaseContext the
pipeline always produces the same output.
"""

from decimal import Decimal

INTELLIGENCE_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Amount bands (INR) — used by prediction, strategy and risk classification
# ---------------------------------------------------------------------------
AMOUNT_BAND_MICRO_MAX = Decimal("5000")     # <= 5,000
AMOUNT_BAND_SMALL_MAX = Decimal("15000")    # <= 15,000
AMOUNT_BAND_MEDIUM_MAX = Decimal("50000")   # <= 50,000
# anything above MEDIUM_MAX is "LARGE"


def amount_band(amount: Decimal) -> str:
    if amount <= AMOUNT_BAND_MICRO_MAX:
        return "MICRO"
    if amount <= AMOUNT_BAND_SMALL_MAX:
        return "SMALL"
    if amount <= AMOUNT_BAND_MEDIUM_MAX:
        return "MEDIUM"
    return "LARGE"


# ---------------------------------------------------------------------------
# Diagnosis — base confidence per matched category
# ---------------------------------------------------------------------------
DIAGNOSIS_BASE_CONFIDENCE = {
    "RISK_BLOCK": 0.90,
    "INSUFFICIENT_FUNDS": 0.88,
    "AUTH_TIMEOUT": 0.80,
    "BANK_DECLINE": 0.80,
    "USER_ABANDONED": 0.75,
    "TECHNICAL_GATEWAY": 0.70,
    "UNKNOWN": 0.25,
}
DIAGNOSIS_MULTI_KEYWORD_BONUS = 0.05   # +5% when >= 2 distinct keywords match
DIAGNOSIS_METHOD_CORROBORATION_BONUS = 0.03
DIAGNOSIS_CONFIDENCE_CAP = 0.95

# Ordered keyword rules. Order encodes priority (safety-first: risk before all).
DIAGNOSIS_KEYWORD_RULES = [
    ("RISK_BLOCK", [
        "fraud", "fraudulent", "risk", "risk_check", "risk engine", "suspicious",
        "blacklist", "blocked by risk", "security check", "stolen", "flagged",
        "chargeback risk", "velocity",
    ]),
    ("INSUFFICIENT_FUNDS", [
        "insufficient", "insufficient funds", "insufficient_funds", "not enough",
        "low balance", "no balance", "exceeds", "exceeded", "limit exceeded",
        "over limit", "insufficient balance", "funds",
    ]),
    ("AUTH_TIMEOUT", [
        "timeout", "timed out", "time out", "expired", "no response",
        "not completed", "incomplete", "authentication", "authorization",
        "otp", "pin", "3ds", "3d secure", "did not respond", "session expired",
    ]),
    ("BANK_DECLINE", [
        "declined", "decline", "do not honour", "do not honor", "issuer",
        "rejected by bank", "bank refused", "card declined", "not permitted",
        "invalid card", "card_declined", "issuer_declined", "refused",
    ]),
    ("USER_ABANDONED", [
        "abandon", "abandoned", "cancelled by user", "canceled by user",
        "user cancelled", "user canceled", "user dropped", "closed the page",
        "user_cancelled", "customer closed", "back button",
    ]),
    ("TECHNICAL_GATEWAY", [
        "gateway", "gateway_error", "server error", "server_error",
        "internal error", "technical", "processing failed", "unavailable",
        "downstream", "upstream", "connection", "network error", "5xx",
    ]),
]

# Known Razorpay error_code fallbacks when no keyword matched
DIAGNOSIS_ERROR_CODE_FALLBACK = {
    "GATEWAY_ERROR": ("TECHNICAL_GATEWAY", 0.55),
    "SERVER_ERROR": ("TECHNICAL_GATEWAY", 0.60),
}

DIAGNOSIS_REASON_OVERRIDES = {
    "payment_risk_check_failed": ("RISK_BLOCK", 0.92),
    "payment_fraud_check_failed": ("RISK_BLOCK", 0.92),
}

# Failure reason phrasing per category
PROBABLE_CAUSE = {
    "AUTH_TIMEOUT": "Customer authentication/authorisation did not complete in time",
    "INSUFFICIENT_FUNDS": "Insufficient funds or a spending limit on the customer's instrument",
    "BANK_DECLINE": "Payment was declined by the issuing bank",
    "TECHNICAL_GATEWAY": "Temporary technical / payment-gateway error during processing",
    "RISK_BLOCK": "Payment was blocked by risk / fraud checks",
    "USER_ABANDONED": "Customer abandoned the payment before completing it",
    "UNKNOWN": "Failure cause could not be determined from the available data",
}


# ---------------------------------------------------------------------------
# Recovery Prediction — deterministic additive scorecard
# ---------------------------------------------------------------------------
# base_rate(category) + sum(contributions), clamped to [MIN, MAX]
PREDICTION_BASE_RATE = {
    "AUTH_TIMEOUT": 0.72,
    "TECHNICAL_GATEWAY": 0.68,
    "USER_ABANDONED": 0.55,
    "INSUFFICIENT_FUNDS": 0.40,
    "BANK_DECLINE": 0.35,
    "RISK_BLOCK": 0.08,
    "UNKNOWN": 0.30,
}

PREDICTION_PROBABILITY_MIN = 0.02
PREDICTION_PROBABILITY_MAX = 0.98

# Customer success-rate feature
PREDICTION_MIN_HISTORY_FOR_RATE = 2          # need >= 2 settled payments to use rate
PREDICTION_W_SUCCESS_RATE = 0.30            # (success_rate - 0.5) * W

# Attempt-count feature
PREDICTION_ATTEMPT_CONTRIB = {0: 0.05, 1: 0.0, 2: -0.10}
PREDICTION_ATTEMPT_CONTRIB_EXHAUSTED = -0.25  # attempt_count >= 3

# Amount-band feature
PREDICTION_AMOUNT_CONTRIB = {
    "MICRO": 0.05,
    "SMALL": 0.0,
    "MEDIUM": -0.05,
    "LARGE": -0.10,
}

# Payment-method feature
PREDICTION_METHOD_CONTRIB = {
    "upi": 0.03,
    "wallet": 0.02,
    "card": 0.0,
    "netbanking": -0.02,
}

# Time-since-failure feature (hours)
def prediction_recency_contribution(hours: float) -> float:
    if hours < 1:
        return 0.02
    if hours < 24:
        return 0.0
    if hours < 72:
        return -0.05
    return -0.10


PREDICTION_PRIOR_RESOLVED_BONUS = 0.05       # customer has a previously RESOLVED case
PREDICTION_PRIOR_UNRESOLVED_PENALTY = -0.05  # customer has prior unresolved cases

# Band thresholds
PREDICTION_BAND_HIGH_MIN = 0.66
PREDICTION_BAND_MEDIUM_MIN = 0.40

# Prediction confidence build-up
PREDICTION_CONFIDENCE_BASE = 0.45
PREDICTION_CONFIDENCE_HAS_HISTORY = 0.20
PREDICTION_CONFIDENCE_STRONG_DIAGNOSIS = 0.15   # diagnosis confidence >= 0.70
PREDICTION_CONFIDENCE_FIRST_ATTEMPT = 0.10
PREDICTION_CONFIDENCE_HAS_ERROR_CODE = 0.10
PREDICTION_CONFIDENCE_MIN = 0.20
PREDICTION_CONFIDENCE_MAX = 0.95


# ---------------------------------------------------------------------------
# Strategy selector — delay hints (informational only; nothing is executed)
# ---------------------------------------------------------------------------
STRATEGY_RETRY_DELAY_HOURS_TECHNICAL = 6
STRATEGY_RETRY_DELAY_HOURS_FUNDS = 48
STRATEGY_RETRY_DELAY_HOURS_DEFAULT = 24
STRATEGY_OUTREACH_CHANNEL = "email"
STRATEGY_PAYMENT_LINK_CHANNEL = "email"
