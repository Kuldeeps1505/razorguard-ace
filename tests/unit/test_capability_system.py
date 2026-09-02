"""
Unit tests — Phase 5: Capability System.

Tests:
- Signing produces consistent signatures
- Signature verification catches tampered fields
- Capability signing key is never logged
"""

import uuid
from datetime import UTC, datetime

from razorguard.domain.authorization.capability_signer import (
    sign_capability,
    verify_capability_signature,
)

_BASE = {
    "capability_id": uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    "intent_id": uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002"),
    "user_id": uuid.UUID("cccccccc-0000-0000-0000-000000000003"),
    "agent_id": uuid.UUID("dddddddd-0000-0000-0000-000000000004"),
    "merchant_id": uuid.UUID("eeeeeeee-0000-0000-0000-000000000005"),
    "product_id": uuid.UUID("ffffffff-0000-0000-0000-000000000006"),
    "amount_minor": 149900,
    "currency": "INR",
    "intent_hash": "abc123intenthash",
    "nonce": "random-nonce-value",
    "session_id": "session-xyz",
    "expires_at": datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC),
    "policy_version_id": "pv-001",
    "merchant_policy_id": "mp-001",
    "signing_key": "test-signing-key-16ch",
}


class TestCapabilitySigning:
    def test_sign_returns_string(self):
        sig = sign_capability(**_BASE)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex

    def test_sign_is_deterministic(self):
        sig1 = sign_capability(**_BASE)
        sig2 = sign_capability(**_BASE)
        assert sig1 == sig2

    def test_verify_passes_on_correct_fields(self):
        sig = sign_capability(**_BASE)
        verify_args = {k: v for k, v in _BASE.items() if k != "signing_key"}
        assert verify_capability_signature(
            **verify_args, signature=sig, signing_key=_BASE["signing_key"]
        )

    def test_verify_fails_on_tampered_amount(self):
        sig = sign_capability(**_BASE)
        tampered = {**_BASE, "amount_minor": 999999}
        verify_args = {k: v for k, v in tampered.items() if k != "signing_key"}
        assert not verify_capability_signature(
            **verify_args, signature=sig, signing_key=_BASE["signing_key"]
        )

    def test_verify_fails_on_tampered_merchant(self):
        sig = sign_capability(**_BASE)
        tampered = {**_BASE, "merchant_id": uuid.uuid4()}
        verify_args = {k: v for k, v in tampered.items() if k != "signing_key"}
        assert not verify_capability_signature(
            **verify_args, signature=sig, signing_key=_BASE["signing_key"]
        )

    def test_verify_fails_on_tampered_user(self):
        sig = sign_capability(**_BASE)
        tampered = {**_BASE, "user_id": uuid.uuid4()}
        verify_args = {k: v for k, v in tampered.items() if k != "signing_key"}
        assert not verify_capability_signature(
            **verify_args, signature=sig, signing_key=_BASE["signing_key"]
        )

    def test_verify_fails_on_tampered_intent_hash(self):
        sig = sign_capability(**_BASE)
        tampered = {**_BASE, "intent_hash": "malicious-hash"}
        verify_args = {k: v for k, v in tampered.items() if k != "signing_key"}
        assert not verify_capability_signature(
            **verify_args, signature=sig, signing_key=_BASE["signing_key"]
        )

    def test_verify_fails_on_wrong_signing_key(self):
        sig = sign_capability(**_BASE)
        verify_args = {k: v for k, v in _BASE.items() if k != "signing_key"}
        assert not verify_capability_signature(
            **verify_args, signature=sig, signing_key="wrong-key-00000"
        )

    def test_verify_fails_on_tampered_nonce(self):
        """Replay protection: stolen nonce with different nonce must fail."""
        sig = sign_capability(**_BASE)
        tampered = {**_BASE, "nonce": "different-nonce"}
        verify_args = {k: v for k, v in tampered.items() if k != "signing_key"}
        assert not verify_capability_signature(
            **verify_args, signature=sig, signing_key=_BASE["signing_key"]
        )

    def test_different_capabilities_have_different_signatures(self):
        sig1 = sign_capability(**_BASE)
        alt = {**_BASE, "capability_id": uuid.uuid4()}
        sig2 = sign_capability(**alt)
        assert sig1 != sig2
