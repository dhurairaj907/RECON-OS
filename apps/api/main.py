"""
RECON OS — Backend Entry Point

FastAPI application configuration, middleware, and route registration.
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db, SessionLocal, seed_default_merchant
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
        finally:
            db.close()
        logger.info("Database schema initialized and default merchant verified.")
    except Exception as e:
        logger.warning(f"Database auto-initialization skipped or deferred: {e}")

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
