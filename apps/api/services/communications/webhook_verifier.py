"""
RECON OS — Phase 7: Communication Provider Delivery-Webhook Verifier

Same fail-closed HMAC-SHA256 pattern as
integrations/razorpay/webhook_verifier.py, applied to
COMMUNICATION_WEBHOOK_SECRET instead — kept as a separate, small function
(not a shared import) since the two integrations have independent secrets
and independent opt-in-to-unsigned flags; sharing the verifier itself would
couple two unrelated providers together for no benefit.
"""

import hmac
import hashlib
import logging

from config import settings

logger = logging.getLogger("recon.services.communications")


def verify_communication_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = settings.COMMUNICATION_WEBHOOK_SECRET
    if not secret:
        if settings.COMMUNICATION_ALLOW_UNSIGNED_WEBHOOKS:
            logger.warning(
                "COMMUNICATION_WEBHOOK_SECRET is not set and "
                "COMMUNICATION_ALLOW_UNSIGNED_WEBHOOKS=true — accepting an UNSIGNED "
                "delivery webhook (DEV ONLY, never do this in a real deployment)."
            )
            return True
        logger.error(
            "Communication delivery webhook REJECTED: COMMUNICATION_WEBHOOK_SECRET is "
            "not configured."
        )
        return False

    if not signature:
        logger.warning("Communication delivery webhook REJECTED: missing signature header.")
        return False

    try:
        expected = hmac.new(key=secret.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256).hexdigest()
        valid = hmac.compare_digest(expected, signature)
        if not valid:
            logger.warning("Communication delivery webhook REJECTED: signature mismatch.")
        return valid
    except Exception as e:
        logger.error(f"Communication delivery webhook REJECTED: error verifying signature: {e}")
        return False


def verify_brevo_webhook_token(authorization_header: str | None) -> bool:
    """
    Brevo-specific webhook authentication — ADDITIVE to (never a replacement
    for) verify_communication_webhook_signature() above. Brevo's
    transactional webhooks do not compute an HMAC signature of the request
    body the way the generic RECON webhook does; per
    developers.brevo.com/docs/secured-webhooks, Brevo instead sends a static
    Bearer token (configured in Brevo's dashboard) with every call. Verified
    here with a constant-time comparison against BREVO_WEBHOOK_TOKEN.

    Always fail-closed: unlike the generic verifier, there is no
    "allow unsigned" opt-out for this one, and an unconfigured token is
    always a rejection — never logs the token itself.
    """
    token = settings.BREVO_WEBHOOK_TOKEN
    if not token:
        logger.error("Brevo delivery webhook REJECTED: BREVO_WEBHOOK_TOKEN is not configured.")
        return False
    if not authorization_header or not authorization_header.startswith("Bearer "):
        logger.warning("Brevo delivery webhook REJECTED: missing or malformed Authorization header.")
        return False
    provided = authorization_header[len("Bearer "):].strip()
    if not provided:
        return False
    return hmac.compare_digest(provided, token)
