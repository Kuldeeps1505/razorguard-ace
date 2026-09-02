"""
Intent canonicalization — deterministic field normalization.

Before hashing, all fields must be in canonical form:
- strings stripped and lowercased where applicable
- amounts as integer strings
- UUIDs as lowercase hex strings
- currency uppercase

This ensures the same logical transaction always produces
the same hash, regardless of input representation.
"""

import uuid
from datetime import datetime


def canonical_uuid(value: uuid.UUID) -> str:
    return str(value).lower()


def canonical_currency(value: str) -> str:
    return value.strip().upper()


def canonical_category(value: str) -> str:
    return value.strip().lower()


def canonical_amount(value: int) -> str:
    return str(value)


def canonical_datetime(value: datetime) -> str:
    return value.isoformat()


def canonical_payment_method(value: str) -> str:
    return value.strip().upper()


def build_intent_canonical_fields(
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    merchant_id: uuid.UUID,
    product_id: uuid.UUID,
    amount_minor: int,
    currency: str,
    category: str,
    session_id: str,
    expires_at: datetime,
    payment_method: str,
    quantity: int,
) -> list[str]:
    """
    Return the ordered list of canonical string fields used for hashing.

    Order is fixed — any change to order produces a different hash.
    Adding a field here invalidates all existing hashes (intentional for
    protocol changes — create new capability if intent fields change).
    """
    return [
        canonical_uuid(user_id),
        canonical_uuid(agent_id),
        canonical_uuid(merchant_id),
        canonical_uuid(product_id),
        canonical_amount(amount_minor),
        canonical_currency(currency),
        canonical_category(category),
        session_id.strip(),
        canonical_datetime(expires_at),
        canonical_payment_method(payment_method),
        canonical_amount(quantity),
    ]
