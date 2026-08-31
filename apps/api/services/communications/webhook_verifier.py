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
