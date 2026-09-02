"""Focused tests for mandates, quotes, reservations, checkout and chaos controls."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestMandateControls:
    @pytest.mark.asyncio
    async def test_rejects_daily_limit_smaller_than_per_transaction_limit(self):
        from razorguard.application.consent.mandates import create_mandate
        from razorguard.shared.errors import CapabilityInvalidError

        with pytest.raises(CapabilityInvalidError, match="limits"):
            await create_mandate(user_id=uuid.uuid4(), agent_id=uuid.uuid4(), merchant_id=uuid.uuid4(),
                max_amount_per_txn_minor=200_000, max_daily_amount_minor=100_000,
                allowed_categories=[], valid_until=datetime.now(UTC) + timedelta(days=1), session=MagicMock())

    @pytest.mark.asyncio
    async def test_category_or_amount_outside_mandate_is_not_eligible(self):
        from razorguard.application.consent.mandates import get_active_mandate_for_intent
        mandate = SimpleNamespace(allowed_categories=json.dumps(["electronics"]), max_amount_per_txn_minor=100_000)
        session = MagicMock(); session.scalar = AsyncMock(return_value=mandate)
        intent = SimpleNamespace(user_id=uuid.uuid4(), agent_id=uuid.uuid4(), merchant_id=uuid.uuid4(),
                                 final_amount_minor=100_001, category="electronics")
        assert await get_active_mandate_for_intent(intent=intent, session=session) is None

    @pytest.mark.asyncio
    async def test_revoke_marks_mandate_unusable(self):
        from razorguard.application.consent.mandates import revoke_mandate
        mandate = SimpleNamespace(status=None, revoked_at=None)
        session = MagicMock(); session.scalar = AsyncMock(return_value=mandate); session.flush = AsyncMock()
        await revoke_mandate(mandate_id=uuid.uuid4(), user_id=uuid.uuid4(), session=session)
        assert mandate.status.value == "REJECTED"
        assert mandate.revoked_at is not None


class TestQuoteAndReservationModels:
    def test_quote_is_unique_per_intent_and_hash_is_unique(self):
        from razorguard.infrastructure.database.models.commerce_controls import CheckoutQuote
        constraints = " ".join(str(c) for c in CheckoutQuote.__table__.constraints)
        assert "intent_id" in constraints and "quote_hash" in constraints

    def test_budget_reservation_is_unique_per_intent(self):
        from razorguard.infrastructure.database.models.commerce_controls import BudgetReservation
        assert "intent_id" in " ".join(str(c) for c in BudgetReservation.__table__.constraints)

    def test_campaign_reservation_is_bound_to_intent_and_agent(self):
        from razorguard.infrastructure.database.models.commerce_controls import CampaignReservation
        columns = {column.name for column in CampaignReservation.__table__.columns}
        assert {"campaign_id", "intent_id", "agent_id", "expires_at", "consumed_at"} <= columns


class TestCheckoutAndWebhookRecovery:
    @pytest.mark.asyncio
    async def test_checkout_route_runs_pipeline_inline(self, monkeypatch):
        from razorguard.application.payments import checkout_handoff
        from razorguard.interfaces.http.routes.payments import CheckoutRequest, checkout

        intent_id = uuid.uuid4()
        user_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        db = MagicMock()
        redis = MagicMock()
        checkout_pipeline = AsyncMock(return_value={
            "status": "success",
            "transaction_id": str(uuid.uuid4()),
            "razorpay_order_id": "order_demo",
            "amount_minor": 149900,
            "capability_id": str(uuid.uuid4()),
            "policy_decision": "ALLOW",
        })
        monkeypatch.setattr(checkout_handoff, "checkout_and_pay", checkout_pipeline)

        response = await checkout(
            CheckoutRequest(intent_id=intent_id), db, redis, user_id, agent_id
        )

        assert response.status == "success"
        assert response.razorpay_order_id == "order_demo"
        checkout_pipeline.assert_awaited_once()
        assert checkout_pipeline.await_args.kwargs["intent_id"] == intent_id
        assert checkout_pipeline.await_args.kwargs["session"] is db
        assert checkout_pipeline.await_args.kwargs["redis"] is redis

    @pytest.mark.asyncio
    async def test_checkout_handoff_rejects_transaction_without_order(self):
        from razorguard.application.payments.checkout_handoff import get_checkout_handoff
        from razorguard.shared.errors import RazorGuardError
        session = MagicMock(); session.scalar = AsyncMock(return_value=None)
        with pytest.raises(RazorGuardError, match="Checkout"):
            await get_checkout_handoff(transaction_id=uuid.uuid4(), user_id=uuid.uuid4(), session=session)

    def test_webhook_inbox_has_retryable_failure_fields(self):
        from razorguard.infrastructure.database.models.webhook_event import WebhookEvent
        columns = {column.name for column in WebhookEvent.__table__.columns}
        assert {"signature_verified", "processing_status", "error_detail", "raw_payload"} <= columns


class TestChaosDemo:
    @pytest.mark.asyncio
    async def test_timeout_is_unknown_without_side_effect(self):
        from razorguard.interfaces.http.routes.chaos import ChaosRequest, simulate_chaos
        response = await simulate_chaos(ChaosRequest(scenario="provider_timeout"))
        assert response["status"] == "UNKNOWN"
        assert response["side_effects"] is False

    @pytest.mark.asyncio
    async def test_forged_webhook_is_blocked(self):
        from razorguard.interfaces.http.routes.chaos import ChaosRequest, simulate_chaos
        response = await simulate_chaos(ChaosRequest(scenario="forged_webhook"))
        assert response["status"] == "BLOCKED"
