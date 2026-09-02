"""
Intent hashing — cryptographic binding of all intent fields.

The intent_hash is the tamper-detection mechanism.
Changing ANY field (amount, merchant, product, currency, ...)
produces a different hash, invalidating authorization.

This is used in:
1. Intent creation — hash stored with intent
2. Capability issuance — hash bound to capability
3. Final pre-execution validation — hash re-computed and compared
"""

import uuid
from datetime import datetime

from razorguard.domain.intents.canonicalization import build_intent_canonical_fields
from razorguard.shared.security import compute_intent_hash


def hash_intent(
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
) -> str:
    """
    Compute the deterministic intent hash.

    Same inputs ALWAYS produce the same hash.
    Different inputs ALWAYS produce different hashes.
    """
    fields = build_intent_canonical_fields(
        user_id=user_id,
        agent_id=agent_id,
        merchant_id=merchant_id,
        product_id=product_id,
        amount_minor=amount_minor,
        currency=currency,
        category=category,
        session_id=session_id,
        expires_at=expires_at,
        payment_method=payment_method,
        quantity=quantity,
    )
    return compute_intent_hash(*fields)


def verify_intent_hash(
    stored_hash: str,
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
) -> bool:
    """
    Re-compute hash from fields and compare with stored hash.

    Used in final pre-execution validation (TOCTOU defense).
    Returns False if ANY field has changed since hash was created.
    """
    computed = hash_intent(
        user_id=user_id,
        agent_id=agent_id,
        merchant_id=merchant_id,
        product_id=product_id,
        amount_minor=amount_minor,
        currency=currency,
        category=category,
        session_id=session_id,
        expires_at=expires_at,
        payment_method=payment_method,
        quantity=quantity,
    )
    return computed == stored_hash
