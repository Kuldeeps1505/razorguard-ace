"""
Webhook signature verifier.

SECURITY: Never trust a webhook payload without verifying its signature.
Razorpay signs webhooks with HMAC-SHA256.
Constant-time comparison prevents timing attacks.
"""

import hashlib
import hmac

from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.observability.metrics import webhook_forgeries_rejected
from razorguard.shared.config import get_settings
from razorguard.shared.errors import InvalidWebhookError

logger = get_logger(__name__)


def verify_webhook_signature(
    payload_body: bytes,
    signature: str,
) -> None:
    """
    Verify Razorpay webhook signature.

    Raises InvalidWebhookError if signature is invalid.
    Never reveals the reason to the caller (security event logged instead).
    """
    settings = get_settings()
    secret = settings.razorpay_webhook_secret.encode()

    expected = hmac.new(secret, payload_body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature):
        webhook_forgeries_rejected.inc()
        logger.warning("webhook_signature_invalid")
        raise InvalidWebhookError("Signature verification failed")
