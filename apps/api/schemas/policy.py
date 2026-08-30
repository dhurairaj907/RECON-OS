"""
RECON OS — Phase 4 (PROVE): Policy overview schema.

Read-only. RECON OS has one deterministic Policy Engine
(services/intelligence/policy_engine.py) — this describes it, it does not
duplicate or reimplement it. No safe way exists yet to let an operator edit
these thresholds without a second validation path for what the engine
actually enforces, so this stays read-only (see routers/policies.py).
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel


class PolicyRuleInfo(BaseModel):
    rule_id: str
    name: str
    condition: str
    decision: str
    action_restriction: str


class PolicyConfig(BaseModel):
    max_recovery_attempts: int
    contact_window_hours: int
    max_contacts_per_window: int
    auto_approval_amount_limit: float
    currency: str = "INR"


class PolicyOverview(BaseModel):
    config: PolicyConfig
    rules: List[PolicyRuleInfo]
    editable: bool = False
    note: str
