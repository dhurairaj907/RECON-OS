"""
RECON OS — Backend Entry Point

FastAPI application configuration, middleware, and route registration.
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import seed_dev_admin
from config import settings
from database import ensure_default_organization, init_db, SessionLocal, seed_default_merchant
from logging_config import setup_logging
from routers import (
    webhooks_router,
    dashboard_router,
    events_router,
    payments_router,
    customers_router,
    recovery_cases_router,
    audit_logs_router,
    simulator_router,
    health_router,
    intelligence_router,
    actions_router,
    analytics_router,
    policies_router,
    auth_router,
    communications_router,
    users_router,
    ai_router,
    communication_webhooks_router,
    connections_router,
    reconciliation_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup & shutdown lifespan event handler.
    Initializes database tables, structured logging, and default merchant.
    """
    setup_logging()
    logger = logging.getLogger("recon.main")
    logger.info("Initializing RECON OS Backend (Phase 1: CONNECT)...")

    # Initialize DB schemas safely
    try:
        init_db()
        db = SessionLocal()
        try:
            seed_default_merchant(db)
            ensure_default_organization(db)
            seed_dev_admin(db)
        finally:
            db.close()
        logger.info("Database schema initialized and default merchant verified.")
    except Exception as e:
        logger.warning(f"Database auto-initialization skipped or deferred: {e}")

    # Surface Phase 3 Razorpay config state at boot (booleans only — no secret).
    # Settings are read from .env ONCE at process start; restart the backend
    # after changing .env for new credentials to take effect.
    _rzp_configured = bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)
    _rzp_test_key = settings.RAZORPAY_KEY_ID.startswith("rzp_test_")
    logger.info(
        "Razorpay (Phase 3 ACT): configured=%s test_mode=%s test_key=%s "
        "webhook_secret_set=%s allow_unsigned_webhooks=%s simulator_enabled=%s",
        _rzp_configured, settings.RAZORPAY_TEST_MODE, _rzp_test_key,
        bool(settings.RAZORPAY_WEBHOOK_SECRET),
        settings.RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS,
        settings.RECON_SIMULATOR_ENABLED,
    )
    if not settings.RECON_API_KEY:
        logger.warning(
            "RECON_API_KEY is not set — financial action endpoints (propose/execute/"
            "approve/reject/verify-unknown/reconcile) are open to any caller who knows "
            "the URL. Set RECON_API_KEY before exposing this API beyond localhost."
        )

    # Startup diagnostic for the communications provider path — mirrors the
    # Razorpay line above. Root-cause finding: RECON_COMMUNICATIONS_MODE and
    # SMTP_* are loaded from a .env file resolved RELATIVE TO THE PROCESS'S
    # CURRENT WORKING DIRECTORY (pydantic-settings' env_file behavior) —
    # starting uvicorn from a directory other than apps/api silently falls
    # back to every setting's default (mode="fake", no real credentials) with
    # NO error raised anywhere. A "fake" send still returns 200 OK and logs
    # a token, so this failure mode is otherwise invisible. This line makes
    # the ACTUAL resolved mode explicit on every startup instead.
    _smtp_configured = bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)
    logger.info(
        "Communications (Phase 7): mode=%s smtp_configured=%s sms_configured=%s "
        "whatsapp_configured=%s automatic_communications_enabled=%s",
        settings.RECON_COMMUNICATIONS_MODE, _smtp_configured,
        bool(settings.SMS_PROVIDER_WEBHOOK_URL),
        bool(settings.WHATSAPP_PROVIDER_WEBHOOK_URL),
        settings.AUTOMATIC_COMMUNICATIONS_ENABLED,
    )
    if settings.RECON_COMMUNICATIONS_MODE == "real" and not _smtp_configured:
        logger.warning(
            "RECON_COMMUNICATIONS_MODE=real but SMTP_HOST/SMTP_FROM_EMAIL are not set — "
            "every real email send (including password reset) will fail with "
            "NOT_CONFIGURED. If credentials ARE set in your .env, this backend process "
            "likely did not load it — check the working directory it was started from."
        )
    if settings.AUTOMATIC_ACTION_EXECUTION_ENABLED:
        logger.info(
            "AUTOMATIC_ACTION_EXECUTION_ENABLED=true — Policy-APPROVED recovery actions "
            "will execute automatically after analysis, with no manual trigger required."
        )

    yield

    logger.info("RECON OS Backend shutting down...")


app = FastAPI(
    title="RECON OS API",
    description="Autonomous Revenue Recovery and Optimization Network API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
# Session auth is a credentialed cookie (allow_credentials=True below), and
# browsers reject "Access-Control-Allow-Origin: *" combined with credentials
# — so a wildcard fallback here was never actually usable, only misleading.
# An empty CORS_ORIGINS now means exactly what it says: no cross-origin
# browser access (same-origin and non-browser clients are unaffected; CORS
# is enforced by the browser, not the server, and never gates curl/server-
# to-server calls).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    """Baseline response hardening — cheap, safe, applies to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# API Version 1 prefix
API_V1_PREFIX = "/api/v1"

app.include_router(health_router, prefix=API_V1_PREFIX)
app.include_router(health_router)  # Also expose /health at root
app.include_router(webhooks_router, prefix=API_V1_PREFIX)
app.include_router(dashboard_router, prefix=API_V1_PREFIX)
app.include_router(events_router, prefix=API_V1_PREFIX)
app.include_router(payments_router, prefix=API_V1_PREFIX)
app.include_router(customers_router, prefix=API_V1_PREFIX)
app.include_router(recovery_cases_router, prefix=API_V1_PREFIX)
app.include_router(audit_logs_router, prefix=API_V1_PREFIX)
app.include_router(simulator_router, prefix=API_V1_PREFIX)
app.include_router(intelligence_router, prefix=API_V1_PREFIX)
app.include_router(actions_router, prefix=API_V1_PREFIX)
app.include_router(analytics_router, prefix=API_V1_PREFIX)
app.include_router(policies_router, prefix=API_V1_PREFIX)
app.include_router(auth_router, prefix=API_V1_PREFIX)
app.include_router(communications_router, prefix=API_V1_PREFIX)
app.include_router(users_router, prefix=API_V1_PREFIX)
app.include_router(ai_router, prefix=API_V1_PREFIX)
app.include_router(communication_webhooks_router, prefix=API_V1_PREFIX)
app.include_router(connections_router, prefix=API_V1_PREFIX)
app.include_router(reconciliation_router, prefix=API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
