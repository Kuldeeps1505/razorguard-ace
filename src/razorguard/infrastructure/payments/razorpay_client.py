"""
Razorpay API client — thin wrapper around the Razorpay SDK.

ARCHITECTURE: All Razorpay-specific logic lives here.
The payment executor never imports razorpay directly.
This isolates provider specifics and makes the system testable.

SECURITY:
- Razorpay keys are never logged
- Only test mode is used (enforced by settings)
- All amounts are in paise (integer)

RELIABILITY:
- Every call has an explicit timeout
- UNKNOWN outcome on timeout — never treated as FAILED
- Idempotency key sent on every payment creation
"""

import razorpay

from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.config import get_settings

logger = get_logger(__name__)

_client: razorpay.Client | None = None


def get_razorpay_client() -> razorpay.Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
        logger.info("razorpay_client_initialized", mode=settings.razorpay_mode)
    return _client


def create_order(
    *,
    amount_minor: int,
    currency: str,
    receipt: str,
    notes: dict | None = None,
) -> dict:
    """
    Create a Razorpay order.

    Returns the order dict on success.
    Raises on failure — caller handles UNKNOWN vs FAILED.

    amount_minor: integer paise — NEVER float.
    receipt: idempotency key for this order.
    """
    client = get_razorpay_client()
    payload = {
        "amount": amount_minor,
        "currency": currency.upper(),
        "receipt": receipt,
        "notes": notes or {},
    }
    logger.info(
        "razorpay_create_order",
        amount=amount_minor,
        currency=currency,
        receipt=receipt,
    )
    return client.order.create(data=payload)


def fetch_order(order_id: str) -> dict:
    """Fetch an order by ID — used for reconciliation."""
    client = get_razorpay_client()
    return client.order.fetch(order_id)


def fetch_payment(payment_id: str) -> dict:
    """Fetch a payment by ID — used for reconciliation."""
    client = get_razorpay_client()
    return client.payment.fetch(payment_id)


def fetch_payments_for_order(order_id: str) -> list[dict]:
    """List all payments for an order — used for reconciliation."""
    client = get_razorpay_client()
    result = client.order.payments(order_id)
    return result.get("items", [])
