"""
Cryptographic utilities.

All security primitives in one place so they can be audited easily.
NEVER use random.random() or uuid4() for security-sensitive IDs.
"""

import hashlib
import hmac
import secrets
import uuid


def generate_id() -> str:
    """Generate a cryptographically random UUID4 string."""
    return str(uuid.uuid4())


def generate_nonce(nbytes: int = 32) -> str:
    """Generate a URL-safe random nonce (base64-encoded)."""
    return secrets.token_urlsafe(nbytes)


def generate_idempotency_key(*parts: str) -> str:
    """
    Generate a deterministic idempotency key from input parts.

    Same inputs always produce the same key.
    Used for payment deduplication.
    """
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()


def sign_payload(payload: str, key: str) -> str:
    """
    HMAC-SHA256 sign a string payload.

    Used for capability integrity verification.
    """
    return hmac.new(
        key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(payload: str, signature: str, key: str) -> bool:
    """
    Constant-time HMAC signature verification.

    Always use this instead of == to prevent timing attacks.
    """
    expected = sign_payload(payload, key)
    return hmac.compare_digest(expected, signature)


def hash_secret(secret: str) -> str:
    """
    One-way hash for storing credentials/API keys.

    Use bcrypt for passwords (via passlib). This is for API key fingerprints.
    """
    return hashlib.sha256(secret.encode()).hexdigest()


def compute_intent_hash(*fields: str) -> str:
    """
    Deterministic hash binding an intent to its key fields.

    Any field change → different hash → authorization invalidated.
    Fields: user_id, merchant_id, product_id, amount_minor,
            currency, category, session_id, expires_at
    """
    canonical = "|".join(fields)
    return hashlib.sha256(canonical.encode()).hexdigest()
