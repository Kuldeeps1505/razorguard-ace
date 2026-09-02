"""
Unit tests — shared/security.py

Tests for all cryptographic primitives.
These must never depend on external services.
"""

from razorguard.shared.security import (
    compute_intent_hash,
    generate_id,
    generate_idempotency_key,
    generate_nonce,
    hash_secret,
    sign_payload,
    verify_signature,
)


def test_generate_id_is_unique():
    ids = {generate_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_generate_nonce_is_unique():
    nonces = {generate_nonce() for _ in range(100)}
    assert len(nonces) == 100


def test_generate_nonce_min_length():
    nonce = generate_nonce(32)
    assert len(nonce) >= 32


def test_idempotency_key_deterministic():
    key1 = generate_idempotency_key("user-1", "intent-42", "merchant-7")
    key2 = generate_idempotency_key("user-1", "intent-42", "merchant-7")
    assert key1 == key2


def test_idempotency_key_different_inputs():
    key1 = generate_idempotency_key("user-1", "intent-42")
    key2 = generate_idempotency_key("user-1", "intent-43")
    assert key1 != key2


def test_sign_and_verify():
    key = "super-secret-key"
    payload = "user=123|amount=149900|currency=INR"
    sig = sign_payload(payload, key)
    assert verify_signature(payload, sig, key)


def test_verify_wrong_key_fails():
    sig = sign_payload("payload", "correct-key")
    assert not verify_signature("payload", sig, "wrong-key")


def test_verify_tampered_payload_fails():
    sig = sign_payload("original", "key")
    assert not verify_signature("tampered", sig, "key")


def test_hash_secret_is_deterministic():
    assert hash_secret("my-api-key") == hash_secret("my-api-key")


def test_hash_secret_not_reversible():
    raw = "my-api-key"
    hashed = hash_secret(raw)
    assert raw not in hashed
    assert len(hashed) == 64  # sha256 hex


def test_intent_hash_deterministic():
    h1 = compute_intent_hash("u1", "m1", "p1", "149900", "INR", "electronics", "s1", "2026-09-05")
    h2 = compute_intent_hash("u1", "m1", "p1", "149900", "INR", "electronics", "s1", "2026-09-05")
    assert h1 == h2


def test_intent_hash_field_change_invalidates():
    """Changing ANY field must produce a different hash — this is the tamper protection."""
    args = ("u1", "m1", "p1", "149900", "INR", "electronics", "s1", "2026-09-05")
    base_hash = compute_intent_hash(*args)

    # Amount tampered
    tampered = ("u1", "m1", "p1", "999999", "INR", "electronics", "s1", "2026-09-05")
    assert compute_intent_hash(*tampered) != base_hash
    # Merchant substituted
    tampered = ("u1", "m2", "p1", "149900", "INR", "electronics", "s1", "2026-09-05")
    assert compute_intent_hash(*tampered) != base_hash
    # Product substituted
    tampered = ("u1", "m1", "p2", "149900", "INR", "electronics", "s1", "2026-09-05")
    assert compute_intent_hash(*tampered) != base_hash
    # Currency tampered
    tampered = ("u1", "m1", "p1", "149900", "USD", "electronics", "s1", "2026-09-05")
    assert compute_intent_hash(*tampered) != base_hash
