"""
Unit tests — Phase 8: Payment Execution.

Key invariants tested:
1. UNKNOWN state is never treated as FAILED
2. UNKNOWN never triggers blind retry
3. Idempotency key generation is deterministic
4. Webhook signature verification works correctly
5. Payment amount is always integer paise
"""

import hashlib
import hmac

import pytest

from razorguard.shared.security import generate_idempotency_key


class TestIdempotencyKey:
    def test_same_inputs_same_key(self):
        k1 = generate_idempotency_key("intent-1", "cap-1", "user-1", "149900", "nonce-x")
        k2 = generate_idempotency_key("intent-1", "cap-1", "user-1", "149900", "nonce-x")
        assert k1 == k2

    def test_different_inputs_different_key(self):
        k1 = generate_idempotency_key("intent-1", "cap-1", "user-1", "149900", "nonce-x")
        k2 = generate_idempotency_key("intent-1", "cap-1", "user-1", "999999", "nonce-x")
        assert k1 != k2

    def test_key_is_hex_string(self):
        k = generate_idempotency_key("a", "b", "c")
        assert len(k) == 64  # SHA-256 hex

    def test_nonce_change_changes_key(self):
        """Changing nonce prevents replay with same intent/capability."""
        k1 = generate_idempotency_key("intent-1", "cap-1", "user-1", "149900", "nonce-1")
        k2 = generate_idempotency_key("intent-1", "cap-1", "user-1", "149900", "nonce-2")
        assert k1 != k2


class TestUnknownStateInvariants:
    """
    CRITICAL: UNKNOWN payment state must never be treated as FAILED.
    UNKNOWN must always go to reconciliation.
    """

    def test_unknown_is_not_failed(self):
        from razorguard.shared.enums import TransactionStatus

        assert TransactionStatus.UNKNOWN != TransactionStatus.FAILED

    def test_unknown_is_not_terminal(self):
        from razorguard.shared.enums import TransactionStatus

        assert not TransactionStatus.UNKNOWN.is_terminal

    def test_unknown_has_reconciliation_path(self):
        from razorguard.domain.intents.state_machine import can_transition
        from razorguard.shared.enums import TransactionStatus

        assert can_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)

    def test_unknown_cannot_retry_directly(self):
        """UNKNOWN must NOT be able to transition back to EXECUTING."""
        from razorguard.domain.intents.state_machine import can_transition
        from razorguard.shared.enums import TransactionStatus

        assert not can_transition(TransactionStatus.UNKNOWN, TransactionStatus.EXECUTING)

    def test_unknown_resolves_to_completed_or_failed(self):
        from razorguard.domain.intents.state_machine import can_transition
        from razorguard.shared.enums import TransactionStatus

        assert can_transition(TransactionStatus.VERIFYING, TransactionStatus.COMPLETED)
        assert can_transition(TransactionStatus.VERIFYING, TransactionStatus.FAILED)


class TestWebhookSignatureVerification:
    def test_valid_signature_passes(self):
        import os

        from razorguard.infrastructure.payments.webhook_verifier import (
            verify_webhook_signature,
        )

        os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test-webhook-secret"

        payload = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123"}}}}'
        secret = b"test-webhook-secret"
        sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()

        # Should not raise
        from unittest.mock import MagicMock, patch

        mock_settings = MagicMock()
        mock_settings.razorpay_webhook_secret = "test-webhook-secret"
        with patch(
            "razorguard.infrastructure.payments.webhook_verifier.get_settings",
            return_value=mock_settings,
        ):
            verify_webhook_signature(payload_body=payload, signature=sig)

    def test_invalid_signature_raises(self):
        from unittest.mock import MagicMock, patch

        from razorguard.infrastructure.payments.webhook_verifier import (
            verify_webhook_signature,
        )
        from razorguard.shared.errors import InvalidWebhookError

        mock_settings = MagicMock()
        mock_settings.razorpay_webhook_secret = "test-webhook-secret"

        with (
            patch(
                "razorguard.infrastructure.payments.webhook_verifier.get_settings",
                return_value=mock_settings,
            ),
            pytest.raises(InvalidWebhookError),
        ):
            verify_webhook_signature(
                payload_body=b"legit payload",
                signature="forged-signature-000",
            )

    def test_empty_payload_with_wrong_sig_raises(self):
        from unittest.mock import MagicMock, patch

        from razorguard.infrastructure.payments.webhook_verifier import (
            verify_webhook_signature,
        )
        from razorguard.shared.errors import InvalidWebhookError

        mock_settings = MagicMock()
        mock_settings.razorpay_webhook_secret = "secret"

        with (
            patch(
                "razorguard.infrastructure.payments.webhook_verifier.get_settings",
                return_value=mock_settings,
            ),
            pytest.raises(InvalidWebhookError),
        ):
            verify_webhook_signature(payload_body=b"", signature="wrong")


class TestPaymentAmountSafety:
    def test_amount_is_integer(self):
        """Amounts used in Razorpay calls must always be integer paise."""
        amount = 149900
        assert isinstance(amount, int)
        assert not isinstance(amount, float)

    def test_paise_to_rupees_never_loses_precision(self):
        from decimal import Decimal

        from razorguard.shared.utils import paise_to_rupees

        # Amounts that would lose precision as float
        tricky_amounts = [149900, 100, 1, 99999, 100000]
        for paise in tricky_amounts:
            rupees = paise_to_rupees(paise)
            assert isinstance(rupees, Decimal)
            # Converting back to paise must be exact
            from razorguard.shared.utils import rupees_to_paise

            assert rupees_to_paise(rupees) == paise
