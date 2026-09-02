"""
Capability signing and verification.

Every capability is signed with HMAC-SHA256 over all its bound fields.
Changing ANY field after issuance → signature mismatch → REJECTED.

This is the cryptographic integrity layer for capability-based authorization.
The signing key is in settings — never hardcoded, never logged.
"""

import json
import uuid
from datetime import datetime

from razorguard.shared.security import sign_payload, verify_signature


def _capability_payload(
    capability_id: uuid.UUID,
    intent_id: uuid.UUID,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    merchant_id: uuid.UUID,
    product_id: uuid.UUID,
    amount_minor: int,
    currency: str,
    intent_hash: str,
    nonce: str,
    session_id: str,
    expires_at: datetime,
    policy_version_id: str,
    merchant_policy_id: str,
) -> str:
    """
    Deterministic canonical payload for signing.
    Field order is fixed — any reordering would break existing signatures.
    """
    data = {
        "cap_id": str(capability_id),
        "intent_id": str(intent_id),
        "user_id": str(user_id),
        "agent_id": str(agent_id),
        "merchant_id": str(merchant_id),
        "product_id": str(product_id),
        "amount_minor": amount_minor,
        "currency": currency.upper(),
        "intent_hash": intent_hash,
        "nonce": nonce,
        "session_id": session_id,
        "expires_at": expires_at.isoformat(),
        "policy_version_id": policy_version_id,
        "merchant_policy_id": merchant_policy_id,
    }
    # sort_keys ensures deterministic serialization
    return json.dumps(data, sort_keys=True)


def sign_capability(
    capability_id: uuid.UUID,
    intent_id: uuid.UUID,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    merchant_id: uuid.UUID,
    product_id: uuid.UUID,
    amount_minor: int,
    currency: str,
    intent_hash: str,
    nonce: str,
    session_id: str,
    expires_at: datetime,
    policy_version_id: str,
    merchant_policy_id: str,
    signing_key: str,
) -> str:
    """Return HMAC-SHA256 signature for a capability."""
    payload = _capability_payload(
        capability_id=capability_id,
        intent_id=intent_id,
        user_id=user_id,
        agent_id=agent_id,
        merchant_id=merchant_id,
        product_id=product_id,
        amount_minor=amount_minor,
        currency=currency,
        intent_hash=intent_hash,
        nonce=nonce,
        session_id=session_id,
        expires_at=expires_at,
        policy_version_id=policy_version_id,
        merchant_policy_id=merchant_policy_id,
    )
    return sign_payload(payload, signing_key)


def verify_capability_signature(
    capability_id: uuid.UUID,
    intent_id: uuid.UUID,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    merchant_id: uuid.UUID,
    product_id: uuid.UUID,
    amount_minor: int,
    currency: str,
    intent_hash: str,
    nonce: str,
    session_id: str,
    expires_at: datetime,
    policy_version_id: str,
    merchant_policy_id: str,
    signature: str,
    signing_key: str,
) -> bool:
    """
    Verify a capability signature. Constant-time comparison.
    Returns False if the capability has been tampered with.
    """
    payload = _capability_payload(
        capability_id=capability_id,
        intent_id=intent_id,
        user_id=user_id,
        agent_id=agent_id,
        merchant_id=merchant_id,
        product_id=product_id,
        amount_minor=amount_minor,
        currency=currency,
        intent_hash=intent_hash,
        nonce=nonce,
        session_id=session_id,
        expires_at=expires_at,
        policy_version_id=policy_version_id,
        merchant_policy_id=merchant_policy_id,
    )
    return verify_signature(payload, signature, signing_key)
