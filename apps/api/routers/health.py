"""
RECON OS — Health Check Router
"""

import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db

logger = logging.getLogger("recon.routers.health")

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check(response: Response, db: Session = Depends(get_db)):
    """
    Health check endpoint verifying application and database connectivity.

    Returns HTTP 200 when the database is reachable, HTTP 503 otherwise —
    deployment orchestrators (load balancers, k8s liveness/readiness probes)
    key off the STATUS CODE, not the response body, so a degraded DB must
    change the code, not just a JSON field. The underlying exception is
    logged server-side only — never returned to the caller (no internal
    error text / connection details in a public response).
    """
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.error("Health check DB connectivity failed", exc_info=True)
        db_status = "unhealthy"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "online" if db_status == "healthy" else "degraded",
        "service": "recon-os-api",
        "phase": "1 - CONNECT",
        "database": db_status,
    }
