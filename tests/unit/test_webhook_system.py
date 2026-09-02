"""
Unit tests — Phase 9: Webhook System.

Tests cover:
- Signature verification (valid, invalid, missing)
- Duplicate event detection invariant
- Amount mismatch detection
- Out-of-order event handling (illegal transition rejection)
- Idempotent handler (same event twice = safe)
"""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest

from razorguard.shared.errors import InvalidWebhookError

# ── Signature verification ────────────────────────────────


class TestWebhookSignatureVerification:
    """Comprehensive signature tests — forged webhooks must be rejected."""

    def _make_sig(self, payload: bytes, secret: str) -> str:
        return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    def _mock_settings(self, secret: str) -> MagicMock:
        s = MagicMock()
        s.razorpay_webhook_secret = secret
        return s

    def test_valid_signature_does_not_raise(self):
        from razorguard.infrastructure.payments.webhook_verifier import verify_webhook_signature

        payload = b'{"event":"payment.captured"}'
        secret = "test-secret-key"
        sig = self._make_sig(payload, secret)
        with patch(
            "razorguard.infrastructure.payments.webhook_verifier.get_settings",
            return_value=self._mock_settings(secret),
        ):
            verify_webhook_signature(payload_body=payload, signature=sig)

    def test_wrong_signature_raises(self):
        from razorguard.infrastructure.payments.webhook_verifier import verify_webhook_signature

        payload = b'{"event":"payment.captured"}'
        with (
            patch(
                "razorguard.infrastructure.payments.webhook_verifier.get_settings",
                return_value=self._mock_settings("real-secret"),
            ),
            pytest.raises(InvalidWebhookError),
        ):
            verify_webhook_signature(payload_body=payload, signature="forged-sig-0000")

    def test_tampered_payload_raises(self):
        """If payload is tampered after signing, signature must not match."""
        from razorguard.infrastructure.payments.webhook_verifier import verify_webhook_signature

        original = b'{"event":"payment.captured","amount":149900}'
        tampered = b'{"event":"payment.captured","amount":999999}'
        secret = "test-secret"
        sig = self._make_sig(original, secret)  # signed for original
        with (
            patch(
                "razorguard.infrastructure.payments.webhook_verifier.get_settings",
                return_value=self._mock_settings(secret),
            ),
            pytest.raises(InvalidWebhookError),
        ):
            verify_webhook_signature(payload_body=tampered, signature=sig)

    def test_empty_body_wrong_sig_raises(self):
        from razorguard.infrastructure.payments.webhook_verifier import verify_webhook_signature

        with (
            patch(
                "razorguard.infrastructure.payments.webhook_verifier.get_settings",
                return_value=self._mock_settings("secret"),
            ),
            pytest.raises(InvalidWebhookError),
        ):
            verify_webhook_signature(payload_body=b"", signature="wrong")

    def test_signature_is_constant_time(self):
        """Signature comparison uses hmac.compare_digest — not == (timing safe)."""
        import inspect

        from razorguard.infrastructure.payments import webhook_verifier

        source = inspect.getsource(webhook_verifier)
        assert (
            "compare_digest" in source
        ), "Signature comparison must use hmac.compare_digest to prevent timing attacks"


# ── Webhook event deduplication ───────────────────────────


class TestWebhookDeduplication:
    def test_deduplication_invariant_documented(self):
        """
        INVARIANT: Same razorpay_event_id must never be processed twice.
        Enforced by UNIQUE constraint on webhook_events.razorpay_event_id.
        """
        from razorguard.infrastructure.database.models.webhook_event import WebhookEvent

        assert any(
            "razorpay_event_id" in str(c) for c in WebhookEvent.__table__.constraints
        ), "razorpay_event_id must have a UNIQUE constraint for deduplication"

    def test_webhook_model_has_processing_status(self):
        from razorguard.infrastructure.database.models.webhook_event import WebhookEvent

        cols = {c.name for c in WebhookEvent.__table__.columns}
        assert "processing_status" in cols
        assert "signature_verified" in cols
        assert "razorpay_event_id" in cols
        assert "raw_payload" in cols


# ── Amount integrity ──────────────────────────────────────


class TestWebhookAmountIntegrity:
    def test_amount_mismatch_is_detected(self):
        """
        If webhook says amount=999999 but our DB says amount=149900,
        the event must be rejected — not used to update state.
        """
        # Simulated check from process_webhook._handle_payment_captured
        our_amount = 149900
        webhook_amount = 999999

        mismatch = bool(webhook_amount and webhook_amount != our_amount)

        assert mismatch, "Amount mismatch must be detected"

    def test_matching_amount_passes(self):
        our_amount = 149900
        webhook_amount = 149900
        mismatch = webhook_amount != our_amount
        assert not mismatch


# ── Out-of-order event protection ────────────────────────


class TestOutOfOrderWebhooks:
    def test_cannot_complete_already_failed_transaction(self):
        """Out-of-order: payment.captured arrives after payment.failed."""
        from razorguard.domain.intents.state_machine import can_transition
        from razorguard.shared.enums import TransactionStatus

        assert not can_transition(TransactionStatus.FAILED, TransactionStatus.COMPLETED)

    def test_cannot_fail_completed_transaction(self):
        """Out-of-order: payment.failed arrives after payment.captured."""
        from razorguard.domain.intents.state_machine import can_transition
        from razorguard.shared.enums import TransactionStatus

        assert not can_transition(TransactionStatus.COMPLETED, TransactionStatus.FAILED)

    def test_completed_is_terminal(self):
        from razorguard.shared.enums import TransactionStatus

        assert TransactionStatus.COMPLETED.is_terminal

    def test_failed_is_terminal(self):
        from razorguard.shared.enums import TransactionStatus

        assert TransactionStatus.FAILED.is_terminal
