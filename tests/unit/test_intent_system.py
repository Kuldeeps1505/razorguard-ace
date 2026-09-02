"""
Unit tests — Phase 3: Intent System.

Tests cover:
- Money value object validation
- Intent canonicalization determinism
- Intent hashing tamper detection
- State machine legal/illegal transitions
- All terminal → any transition rejected
- UNKNOWN state never terminal (reconciliation path)
"""

import dataclasses
import uuid
from datetime import UTC, datetime

import pytest

from razorguard.domain.intents.exceptions import InvalidIntentValueError
from razorguard.domain.intents.hashing import hash_intent, verify_intent_hash
from razorguard.domain.intents.state_machine import (
    LEGAL_TRANSITIONS,
    IllegalTransitionError,
    can_transition,
    validate_transition,
)
from razorguard.domain.intents.value_objects import IntentProduct, Money
from razorguard.shared.enums import TransactionStatus

# ── Money value object ────────────────────────────────────


class TestMoney:
    def test_valid_money(self):
        m = Money(amount_minor=149900, currency="INR")
        assert m.amount_minor == 149900
        assert m.currency == "INR"

    def test_rejects_float(self):
        with pytest.raises((InvalidIntentValueError, TypeError)):
            Money(amount_minor=1499.00, currency="INR")  # type: ignore

    def test_rejects_zero(self):
        with pytest.raises(InvalidIntentValueError):
            Money(amount_minor=0, currency="INR")

    def test_rejects_negative(self):
        with pytest.raises(InvalidIntentValueError):
            Money(amount_minor=-100, currency="INR")

    def test_rejects_too_large(self):
        with pytest.raises(InvalidIntentValueError):
            Money(amount_minor=999_999_999, currency="INR")

    def test_rejects_unsupported_currency(self):
        with pytest.raises(InvalidIntentValueError):
            Money(amount_minor=100, currency="USD")

    def test_as_rupees(self):
        from decimal import Decimal

        m = Money(amount_minor=149900, currency="INR")
        assert m.as_rupees == Decimal("1499.00")

    def test_str_representation(self):
        m = Money(amount_minor=149900, currency="INR")
        assert "1499.00" in str(m)

    def test_subtract_discount(self):
        m = Money(amount_minor=149900, currency="INR")
        result = m.subtract_discount(10000)
        assert result.amount_minor == 139900

    def test_subtract_discount_rejects_full_amount(self):
        m = Money(amount_minor=100, currency="INR")
        with pytest.raises(InvalidIntentValueError):
            m.subtract_discount(100)

    def test_immutable(self):
        m = Money(amount_minor=100, currency="INR")
        with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            m.amount_minor = 200  # type: ignore


# ── IntentProduct value object ────────────────────────────


class TestIntentProduct:
    def test_valid(self):
        p = IntentProduct(
            product_id=uuid.uuid4(),
            merchant_id=uuid.uuid4(),
            category="electronics",
            quantity=1,
        )
        assert p.quantity == 1

    def test_rejects_zero_quantity(self):
        with pytest.raises(InvalidIntentValueError):
            IntentProduct(
                product_id=uuid.uuid4(),
                merchant_id=uuid.uuid4(),
                category="electronics",
                quantity=0,
            )

    def test_rejects_empty_category(self):
        with pytest.raises(InvalidIntentValueError):
            IntentProduct(
                product_id=uuid.uuid4(),
                merchant_id=uuid.uuid4(),
                category="   ",
                quantity=1,
            )


# ── Intent hashing ────────────────────────────────────────

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


class TestIntentHashing:
    def test_deterministic(self):
        h1 = hash_intent(**HASH_BASE)
        h2 = hash_intent(**HASH_BASE)
        assert h1 == h2

    def test_amount_tamper_detected(self):
        original = hash_intent(**HASH_BASE)
        tampered = {**HASH_BASE, "amount_minor": 999999}
        assert hash_intent(**tampered) != original

    def test_merchant_substitution_detected(self):
        original = hash_intent(**HASH_BASE)
        tampered = {**HASH_BASE, "merchant_id": uuid.uuid4()}
        assert hash_intent(**tampered) != original

    def test_product_substitution_detected(self):
        original = hash_intent(**HASH_BASE)
        tampered = {**HASH_BASE, "product_id": uuid.uuid4()}
        assert hash_intent(**tampered) != original

    def test_currency_tamper_detected(self):
        # INR → any other currency should be rejected by Money, but hash must differ too
        original = hash_intent(**HASH_BASE)
        # bypass Money validation, test hashing directly
        tampered = {**HASH_BASE, "currency": "USD"}
        assert hash_intent(**tampered) != original

    def test_user_substitution_detected(self):
        original = hash_intent(**HASH_BASE)
        tampered = {**HASH_BASE, "user_id": uuid.uuid4()}
        assert hash_intent(**tampered) != original

    def test_verify_passes_on_unchanged_fields(self):
        h = hash_intent(**HASH_BASE)
        assert verify_intent_hash(stored_hash=h, **HASH_BASE)

    def test_verify_fails_on_tampered_amount(self):
        h = hash_intent(**HASH_BASE)
        tampered = {**HASH_BASE, "amount_minor": 999999}
        assert not verify_intent_hash(stored_hash=h, **tampered)


# ── State machine ─────────────────────────────────────────


class TestStateMachine:
    def test_created_to_validating_legal(self):
        validate_transition(TransactionStatus.CREATED, TransactionStatus.VALIDATING)

    def test_submitted_to_completed_legal(self):
        validate_transition(TransactionStatus.SUBMITTED, TransactionStatus.COMPLETED)

    def test_executing_to_unknown_legal(self):
        """UNKNOWN is the network-timeout path — must be legal."""
        validate_transition(TransactionStatus.EXECUTING, TransactionStatus.UNKNOWN)

    def test_unknown_to_verifying_legal(self):
        """UNKNOWN must have a reconciliation path — never stuck."""
        validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)

    def test_terminal_to_any_illegal(self):
        """Terminal states must NEVER transition out."""
        terminal = [s for s in TransactionStatus if s.is_terminal]
        for t in terminal:
            for target in TransactionStatus:
                assert not can_transition(
                    t, target
                ), f"Terminal state {t} should not transition to {target}"

    def test_completed_to_executing_illegal(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.COMPLETED, TransactionStatus.EXECUTING)

    def test_failed_to_authorized_illegal(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.FAILED, TransactionStatus.AUTHORIZED)

    def test_created_to_completed_illegal(self):
        """Cannot skip the authorization steps."""
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.CREATED, TransactionStatus.COMPLETED)

    def test_can_transition_returns_bool(self):
        assert can_transition(TransactionStatus.CREATED, TransactionStatus.VALIDATING) is True
        assert can_transition(TransactionStatus.COMPLETED, TransactionStatus.EXECUTING) is False

    def test_all_legal_transitions_defined(self):
        """Smoke test — legal transitions set must be non-empty."""
        assert len(LEGAL_TRANSITIONS) > 10

    def test_unknown_not_in_terminal_set(self):
        """Regression test — UNKNOWN must never be classified as terminal."""
        assert not TransactionStatus.UNKNOWN.is_terminal
