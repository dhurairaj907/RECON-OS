"""
RECON OS — Phase 4: Minimal endpoint protection for financially-sensitive routes

Two independent, deliberately small controls, applied ONLY to endpoints that
propose, execute, approve, reject, verify, or reconcile a recovery action
(never read-only GETs, and never as a substitute for the Policy Engine /
idempotency guards those endpoints already enforce — this sits in front of
them, it does not replace them):

  1. A shared API key (`RECON_API_KEY`) — a request must present it in the
     `X-RECON-API-KEY` header to reach a protected endpoint. Deliberately NOT
     a full user/identity system: RECON OS has one seeded demo merchant and
     no user accounts, so a per-user auth system would be scope well beyond
     what the product needs. This is the smallest control that stops "anyone
     who finds the URL" from triggering a financial action. It is unset
     (open) by default so local development and demos keep working out of
     the box; a warning is logged once when a request reaches a protected
     endpoint with no key configured, and operators are expected to set
     RECON_API_KEY before exposing the API beyond localhost.

  2. A simple in-memory per-client-IP rate limiter for the same endpoints —
     bounds how fast one caller can attempt financial actions. In-memory and
     per-process by design (this is a single-process demo deployment, not a
     horizontally-scaled service); a production multi-instance deployment
     would need a shared store (e.g. Redis) instead of this dict.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request, status

from config import settings

logger = logging.getLogger("recon.security")

_warned_unset = False


def require_api_key(x_recon_api_key: str | None = Header(default=None, alias="X-RECON-API-KEY")) -> None:
    """FastAPI dependency gating financially-sensitive endpoints. No-op
    (open) when RECON_API_KEY is unset — see module docstring."""
    global _warned_unset
    if not settings.RECON_API_KEY:
        if not _warned_unset:
            logger.warning(
                "RECON_API_KEY is not set — financial action endpoints are UNPROTECTED "
                "beyond the Policy Engine itself. Set RECON_API_KEY before exposing this "
                "API beyond localhost."
            )
            _warned_unset = True
        return
    if x_recon_api_key != settings.RECON_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )


_RATE_WINDOW_SECONDS = 60.0
_request_log: dict[str, deque] = defaultdict(deque)


def _check_rate(log: dict[str, deque], client_key: str, limit: int, window_seconds: float) -> None:
    now = time.monotonic()
    q = log[client_key]
    while q and now - q[0] > window_seconds:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded ({limit} requests) for this operation.",
        )
    q.append(now)


def rate_limit(request: Request) -> None:
    """Bounds financial-action attempts per client IP. In-memory, per-process
    — see module docstring for the multi-instance limitation. Disabled by
    setting RECON_RATE_LIMIT_PER_MINUTE to 0."""
    limit = int(settings.RECON_RATE_LIMIT_PER_MINUTE)
    if limit <= 0:
        return
    client_key = request.client.host if request.client else "unknown"
    _check_rate(_request_log, client_key, limit, _RATE_WINDOW_SECONDS)


# --- Phase 7: password-reset request rate limiting -------------------------
# A SEPARATE bucket/window from the financial-action limiter above (different
# semantics — this bounds account-enumeration/reset-spam attempts, not
# recovery-action throughput) so tuning one never silently affects the other.
_RESET_WINDOW_SECONDS = 3600.0
_reset_request_log: dict[str, deque] = defaultdict(deque)


def password_reset_rate_limit(request: Request) -> None:
    """Bounds forgot-password attempts per client IP. Disabled by setting
    PASSWORD_RESET_RATE_LIMIT_PER_HOUR to 0."""
    limit = int(settings.PASSWORD_RESET_RATE_LIMIT_PER_HOUR)
    if limit <= 0:
        return
    client_key = request.client.host if request.client else "unknown"
    _check_rate(_reset_request_log, client_key, limit, _RESET_WINDOW_SECONDS)
