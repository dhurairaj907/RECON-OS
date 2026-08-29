"""
RECON OS — Phase 3 (ACT) Action Domain

    Strategy  ->  Policy  ->  ActionProposal  ->  Action Executor  ->  Razorpay Adapter  ->  Razorpay API

Hard rules:
  * The deterministic Policy Engine is authoritative. The Action Executor
    RE-EVALUATES policy server-side before any Razorpay call — a frontend- or
    AI-supplied "approved" value is never trusted.
  * Only CREATE_PAYMENT_LINK is executable, and only against Razorpay TEST MODE.
  * Creating a Payment Link is NOT revenue recovered. Recovery is confirmed only
    by a `payment_link.paid` webhook.
  * Missing Razorpay credentials never crash the app — execution returns a
    structured BLOCKED result.
"""

from services.actions.proposal import build_proposal, get_or_create_action
from services.actions.executor import execute_action
from services.actions.verification import verify_payment_link_recovery

__all__ = [
    "build_proposal",
    "get_or_create_action",
    "execute_action",
    "verify_payment_link_recovery",
]
