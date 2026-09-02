"""
RECON OS — Merchant Connections/Integrations status  (read-only)

    GET /api/v1/connections

Answers "is Razorpay actually connected, and when did we last hear from
it?" and the same for Email/SMS/WhatsApp — using ONLY existing config
(config.settings), the existing Razorpay adapter, and the existing,
already-populated RevenueEvent table. No new credential-storage model, no
secret exposure (only booleans/non-secret metadata), organization-scoped
exactly like every other resource (get_org_merchant).

This is the read-only status half of the "Connections" concept — editing
provider credentials (connect/disconnect/reconfigure) is NOT implemented
here: RECON OS has no per-organization encrypted secret store today, and
building one is a genuinely separate, security-critical feature this
change deliberately does not attempt (see the phase report). Credentials
remain server-side environment configuration only, exactly as in every
prior phase.
"""

from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from auth import AuthContext, get_auth_context
from config import settings
from database import get_db, get_org_merchant
from integrations.razorpay.adapter import get_razorpay_adapter
from models.revenue_event import RevenueEvent
from schemas.connections import (
    AutomationStatus,
    ConnectionsOverview,
    EmailConnectionStatus,
    RazorpayConnectionStatus,
    SmsConnectionStatus,
    WhatsAppConnectionStatus,
)

router = APIRouter(tags=["Connections"])


@router.get("/connections", response_model=ConnectionsOverview)
def get_connections_overview(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    merchant = get_org_merchant(db, ctx.organization)
    adapter = get_razorpay_adapter()

    events = (
        db.query(RevenueEvent)
        .filter(RevenueEvent.merchant_id == merchant.id, RevenueEvent.source == "razorpay")
        .order_by(desc(RevenueEvent.received_at))
        .limit(200)
        .all()
    )
    last_event_at = events[0].received_at if events else None
    last_success = next((e for e in events if e.processing_status == "processed"), None)
    last_failure = next((e for e in events if e.processing_status not in ("processed", "received")), None)

    if not adapter.is_configured():
        rzp_status = "NOT_CONFIGURED"
    elif not adapter.is_test_key() and adapter.test_mode:
        rzp_status = "INVALID_CREDENTIALS"
    elif not settings.RAZORPAY_WEBHOOK_SECRET and not settings.RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS:
        rzp_status = "WEBHOOK_NOT_CONFIGURED"
    else:
        rzp_status = "CONNECTED"

    razorpay = RazorpayConnectionStatus(
        status=rzp_status,
        connection_scope=(
            "Platform-wide, single connected organization — this Razorpay credential is "
            "shared server-side configuration, not a per-organization merchant connection. "
            "RECON OS has no per-organization encrypted credential store today; a "
            "production multi-merchant deployment would need one before a second "
            "organization could connect its own Razorpay account."
        ),
        configured=adapter.is_configured(),
        test_mode=bool(adapter.test_mode),
        test_key=bool(adapter.is_test_key()) if adapter.is_configured() else False,
        webhook_secret_set=bool(settings.RAZORPAY_WEBHOOK_SECRET),
        allow_unsigned_webhooks=bool(settings.RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS),
        simulator_enabled=bool(settings.RECON_SIMULATOR_ENABLED),
        last_event_at=last_event_at,
        last_success_at=last_success.received_at if last_success else None,
        last_failure_at=last_failure.received_at if last_failure else None,
        last_error=(last_failure.error_message[:300] if last_failure and last_failure.error_message else None),
        events_received_total=len(events),
    )

    smtp_configured = bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)
    email = EmailConnectionStatus(
        status="CONNECTED" if (settings.RECON_COMMUNICATIONS_MODE == "real" and smtp_configured)
               else "FAKE_MODE" if settings.RECON_COMMUNICATIONS_MODE == "fake" else "NOT_CONFIGURED",
        mode=settings.RECON_COMMUNICATIONS_MODE, configured=smtp_configured,
        smtp_host_set=bool(settings.SMTP_HOST), use_ssl=bool(settings.SMTP_USE_SSL),
    )
    sms_configured = bool(settings.SMS_PROVIDER_WEBHOOK_URL)
    sms = SmsConnectionStatus(
        status="CONNECTED" if (settings.RECON_COMMUNICATIONS_MODE == "real" and sms_configured)
               else "FAKE_MODE" if settings.RECON_COMMUNICATIONS_MODE == "fake" else "NOT_CONFIGURED",
        mode=settings.RECON_COMMUNICATIONS_MODE, configured=sms_configured,
    )
    whatsapp_configured = bool(settings.WHATSAPP_PROVIDER_WEBHOOK_URL)
    whatsapp = WhatsAppConnectionStatus(
        status="CONNECTED" if (settings.RECON_COMMUNICATIONS_MODE == "real" and whatsapp_configured)
               else "FAKE_MODE" if settings.RECON_COMMUNICATIONS_MODE == "fake" else "NOT_CONFIGURED",
        mode=settings.RECON_COMMUNICATIONS_MODE, configured=whatsapp_configured,
        require_template=bool(settings.WHATSAPP_REQUIRE_TEMPLATE),
    )

    automation = AutomationStatus(
        automatic_action_execution_enabled=bool(settings.AUTOMATIC_ACTION_EXECUTION_ENABLED),
        automatic_communications_enabled=bool(settings.AUTOMATIC_COMMUNICATIONS_ENABLED),
    )

    return ConnectionsOverview(razorpay=razorpay, email=email, sms=sms, whatsapp=whatsapp, automation=automation)
