"""
RECON OS — Merchant Connections/Integrations status  (read-only)

Every field here is computed from EXISTING sources — server-side config
(config.settings), the existing Razorpay adapter, and the existing
RevenueEvent table (already populated by the real webhook handler and the
Simulator) — never a new credential-storage model, never a fabricated
status. Secrets are NEVER included; only booleans/non-secret metadata (test
mode, whether a value is set, timestamps, counts).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RazorpayConnectionStatus(BaseModel):
    status: str            # CONNECTED | NOT_CONFIGURED | INVALID_CREDENTIALS | WEBHOOK_NOT_CONFIGURED
    # Honest, server-computed description of what "connected" means today —
    # a single platform-wide credential, not a per-organization merchant
    # connection. Machine-readable so it can't drift from reality the way a
    # frontend-only disclaimer could.
    connection_scope: str
    configured: bool
    test_mode: bool
    test_key: bool
    webhook_secret_set: bool
    allow_unsigned_webhooks: bool
    simulator_enabled: bool
    last_event_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_error: Optional[str] = None
    events_received_total: int = 0


class EmailConnectionStatus(BaseModel):
    status: str             # CONNECTED | NOT_CONFIGURED | FAKE_MODE
    mode: str                # "real" | "fake"
    configured: bool
    smtp_host_set: bool
    use_ssl: bool


class SmsConnectionStatus(BaseModel):
    status: str
    mode: str
    configured: bool


class WhatsAppConnectionStatus(BaseModel):
    status: str
    mode: str
    configured: bool
    require_template: bool


class AutomationStatus(BaseModel):
    automatic_action_execution_enabled: bool
    automatic_communications_enabled: bool


class ConnectionsOverview(BaseModel):
    razorpay: RazorpayConnectionStatus
    email: EmailConnectionStatus
    sms: SmsConnectionStatus
    whatsapp: WhatsAppConnectionStatus
    automation: AutomationStatus
