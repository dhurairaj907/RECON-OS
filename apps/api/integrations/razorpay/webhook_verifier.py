"""
RECON OS — Razorpay Webhook Verifier

Validates HMAC SHA-256 webhook signatures against the configured secret.
IMPORTANT: Always uses the RAW request bytes, never parsed/reconstructed JSON.
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
        bool: True if signature is valid, False otherwise.
    """
    webhook_secret = secret if secret is not None else settings.RAZORPAY_WEBHOOK_SECRET

    if not webhook_secret:
        logger.warning("RAZORPAY_WEBHOOK_SECRET is not configured. Webhook signature verification skipped in dev mode.")
        return True

    if not signature:
        logger.warning("Missing X-Razorpay-Signature header in webhook request.")
        return False

    try:
        expected_signature = hmac.new(
            key=webhook_secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        is_valid = hmac.compare_digest(expected_signature, signature)
        if not is_valid:
            logger.warning("Razorpay webhook signature mismatch.")
        return is_valid
    except Exception as e:
        logger.error(f"Error during webhook signature verification: {e}")
        return False
