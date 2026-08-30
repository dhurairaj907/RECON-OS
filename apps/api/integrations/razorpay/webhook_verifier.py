"""
RECON OS — Razorpay Webhook Verifier

Validates HMAC SHA-256 webhook signatures against the configured secret.
IMPORTANT: Always uses the RAW request bytes, never parsed/reconstructed JSON.

FAIL-CLOSED: an inbound webhook is rejected unless it carries a valid signature
verified against RAZORPAY_WEBHOOK_SECRET. Unsigned webhooks are accepted ONLY
when RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS=true is explicitly set (local dev only).
"""

import hmac
import hashlib
import logging

from config import settings

logger = logging.getLogger("recon.integrations.razorpay")


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str = None) -> bool:
    """
    Verifies that the incoming webhook signature matches the HMAC SHA256 of raw_body.

    Args:
        raw_body: The unparsed raw HTTP request body as bytes.
        signature: The 'X-Razorpay-Signature' header value from Razorpay.
        secret: Optional secret override; defaults to settings.RAZORPAY_WEBHOOK_SECRET.

    Returns:
        bool: True only if the signature is present and valid (or, in explicit
              dev mode, if unsigned webhooks are allowed and no secret is set).
    """
    webhook_secret = secret if secret is not None else settings.RAZORPAY_WEBHOOK_SECRET

    if not webhook_secret:
        if settings.RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS:
            logger.warning(
                "RAZORPAY_WEBHOOK_SECRET is not set and RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS=true "
                "— accepting an UNSIGNED webhook (DEV ONLY, never do this in a real deployment)."
            )
            return True
        logger.error(
            "Webhook REJECTED: RAZORPAY_WEBHOOK_SECRET is not configured. "
            "Set it (and register the webhook in the Razorpay dashboard) to accept webhooks."
        )
        return False

    if not signature:
        logger.warning("Webhook REJECTED: missing X-Razorpay-Signature header.")
        return False

    try:
        expected_signature = hmac.new(
            key=webhook_secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(expected_signature, signature)
        if not is_valid:
            logger.warning("Webhook REJECTED: Razorpay signature mismatch.")
        return is_valid
    except Exception as e:
        logger.error(f"Webhook REJECTED: error during signature verification: {e}")
        return False
