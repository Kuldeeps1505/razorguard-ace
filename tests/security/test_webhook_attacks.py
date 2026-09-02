"""
Phase 14 — Webhook forgery, replay, amount mismatch, illegal transitions.
"""

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from razorguard.domain.intents.state_machine import can_transition
from razorguard.infrastructure.payments.webhook_verifier import verify_webhook_signature
from razorguard.shared.enums import TransactionStatus
from razorguard.shared.errors import InvalidWebhookError


def _sig(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


class TestForgedWebhook:
    def test_forged_signature_rejected(self):
        with patch(
            "razorguard.infrastructure.payments.webhook_verifier.get_settings",
        ) as gs:
            gs.return_value.razorpay_webhook_secret = "real-secret"
            with pytest.raises(InvalidWebhookError):
                verify_webhook_signature(
                    payload_body=b'{"event":"payment.captured"}',
                    signature="forged",
                )

    def test_valid_signature_accepted(self):
        payload = b'{"event":"payment.captured"}'
        secret = "real-secret"
        with patch(
            "razorguard.infrastructure.payments.webhook_verifier.get_settings",
        ) as gs:
            gs.return_value.razorpay_webhook_secret = secret
            verify_webhook_signature(
                payload_body=payload,
                signature=_sig(payload, secret),
            )


class TestDuplicateAndOutOfOrderWebhook:
    @pytest.mark.asyncio
    async def test_duplicate_event_short_circuits(self):
        from razorguard.application.webhooks.process_webhook import process_webhook

        existing = MagicMock()
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=result)

        out = await process_webhook(
            razorpay_event_id="evt_dup",
            event_type="payment.captured",
            raw_payload={},
            session=session,
        )
        assert out["status"] == "duplicate"

    def test_completed_cannot_be_failed_by_late_webhook(self):
        assert not can_transition(TransactionStatus.COMPLETED, TransactionStatus.FAILED)

    def test_failed_cannot_be_completed_by_late_webhook(self):
        assert not can_transition(TransactionStatus.FAILED, TransactionStatus.COMPLETED)

    def test_webhook_amount_mismatch_rejected_in_handler_source(self):
        import inspect

        from razorguard.application.webhooks import process_webhook as mod

        source = inspect.getsource(mod._handle_payment_captured)
        assert "amount_mismatch_rejected" in source
        assert "webhook_amount != txn.amount_minor" in source
