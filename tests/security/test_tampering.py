"""
Phase 14 — Amount / currency / product / merchant tampering.

Intent hash and capability signature bind canonical fields.
Any substitution invalidates authorization.
"""

import uuid
from datetime import UTC, datetime

from razorguard.domain.authorization.capability_signer import (
    sign_capability,
    verify_capability_signature,
)
from razorguard.domain.intents.hashing import hash_intent, verify_intent_hash

HASH_BASE = {
    "user_id": uuid.UUID("11111111-0000-0000-0000-000000000001"),
    "agent_id": uuid.UUID("22222222-0000-0000-0000-000000000002"),
    "merchant_id": uuid.UUID("33333333-0000-0000-0000-000000000003"),
    "product_id": uuid.UUID("44444444-0000-0000-0000-000000000004"),
    "amount_minor": 149900,
    "currency": "INR",
    "category": "electronics",
    "session_id": "sess-abc-123",
    "expires_at": datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC),
    "payment_method": "UPI",
    "quantity": 1,
}

SIG_BASE = {
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


class TestIntentFieldTampering:
    def test_amount_tampering_breaks_hash(self):
        stored = hash_intent(**HASH_BASE)
        assert not verify_intent_hash(stored, **{**HASH_BASE, "amount_minor": 999999})

    def test_currency_tampering_breaks_hash(self):
        stored = hash_intent(**HASH_BASE)
        assert not verify_intent_hash(stored, **{**HASH_BASE, "currency": "USD"})

    def test_product_substitution_breaks_hash(self):
        stored = hash_intent(**HASH_BASE)
        assert not verify_intent_hash(stored, **{**HASH_BASE, "product_id": uuid.uuid4()})

    def test_merchant_substitution_breaks_hash(self):
        stored = hash_intent(**HASH_BASE)
        assert not verify_intent_hash(stored, **{**HASH_BASE, "merchant_id": uuid.uuid4()})

    def test_untampered_hash_verifies(self):
        stored = hash_intent(**HASH_BASE)
        assert verify_intent_hash(stored, **HASH_BASE)


class TestCapabilityFieldTampering:
    def test_amount_tampering_fails_signature(self):
        sig = sign_capability(**SIG_BASE)
        args = {k: v for k, v in SIG_BASE.items() if k != "signing_key"}
        args["amount_minor"] = 1
        assert not verify_capability_signature(
            **args, signature=sig, signing_key=SIG_BASE["signing_key"]
        )

    def test_currency_tampering_fails_signature(self):
        sig = sign_capability(**SIG_BASE)
        args = {k: v for k, v in SIG_BASE.items() if k != "signing_key"}
        args["currency"] = "USD"
        assert not verify_capability_signature(
            **args, signature=sig, signing_key=SIG_BASE["signing_key"]
        )

    def test_product_substitution_fails_signature(self):
        sig = sign_capability(**SIG_BASE)
        args = {k: v for k, v in SIG_BASE.items() if k != "signing_key"}
        args["product_id"] = uuid.uuid4()
        assert not verify_capability_signature(
            **args, signature=sig, signing_key=SIG_BASE["signing_key"]
        )

    def test_merchant_substitution_fails_signature(self):
        sig = sign_capability(**SIG_BASE)
        args = {k: v for k, v in SIG_BASE.items() if k != "signing_key"}
        args["merchant_id"] = uuid.uuid4()
        assert not verify_capability_signature(
            **args, signature=sig, signing_key=SIG_BASE["signing_key"]
        )
