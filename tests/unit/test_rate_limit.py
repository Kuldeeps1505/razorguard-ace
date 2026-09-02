"""
Unit tests for the RateLimiter dependency.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from razorguard.interfaces.http.middleware.rate_limit import RateLimiter
from razorguard.shared.config import Settings
from razorguard.shared.errors import RateLimitExceededError


@pytest.mark.asyncio
class TestRateLimiterDependency:
    async def test_rate_limiter_by_client_ip(self):
        # Setup mocks
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = "192.168.1.50"
        request.state = MagicMock()
        del request.state.user_id  # Ensure user_id is not set

        redis_mock = AsyncMock()
        settings = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            razorpay_key_id="rzp_test_id",
            razorpay_key_secret="rzp_test_secret",
            razorpay_webhook_secret="rzp_test_webhook_secret",
            app_secret_key="x" * 32,
            jwt_secret_key="y" * 32,
            capability_signing_key="z" * 16,
            rate_limit_api_per_minute=100,
        )

        limiter = RateLimiter("api")

        with patch(
            "razorguard.interfaces.http.middleware.rate_limit.check_rate_limit"
        ) as mock_check:
            await limiter(request=request, redis=redis_mock, settings=settings)
            mock_check.assert_called_once_with(
                redis=redis_mock,
                scope="api",
                identifier="192.168.1.50",
                limit=100,
                window_seconds=60,
            )

    async def test_rate_limiter_by_authenticated_user(self):
        # Setup mocks
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = "192.168.1.50"
        request.state = MagicMock()
        request.state.user_id = "user_abc_123"

        redis_mock = AsyncMock()
        settings = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            razorpay_key_id="rzp_test_id",
            razorpay_key_secret="rzp_test_secret",
            razorpay_webhook_secret="rzp_test_webhook_secret",
            app_secret_key="x" * 32,
            jwt_secret_key="y" * 32,
            capability_signing_key="z" * 16,
            rate_limit_payment_per_minute=10,
        )

        limiter = RateLimiter("payment")

        with patch(
            "razorguard.interfaces.http.middleware.rate_limit.check_rate_limit"
        ) as mock_check:
            await limiter(request=request, redis=redis_mock, settings=settings)
            mock_check.assert_called_once_with(
                redis=redis_mock,
                scope="payment",
                identifier="user_abc_123",
                limit=10,
                window_seconds=60,
            )

    async def test_rate_limiter_bypasses_in_testing_without_redis(self):
        request = MagicMock(spec=Request)
        settings = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            razorpay_key_id="rzp_test_id",
            razorpay_key_secret="rzp_test_secret",
            razorpay_webhook_secret="rzp_test_webhook_secret",
            app_secret_key="x" * 32,
            jwt_secret_key="y" * 32,
            capability_signing_key="z" * 16,
            app_env="testing",
        )

        limiter = RateLimiter("api")
        # Ensure no exception is raised and check_rate_limit is not called
        with patch(
            "razorguard.interfaces.http.middleware.rate_limit.check_rate_limit"
        ) as mock_check:
            await limiter(request=request, redis=None, settings=settings)
            mock_check.assert_not_called()

    async def test_rate_limiter_propagates_exceeded_error(self):
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.state = MagicMock()
        del request.state.user_id

        redis_mock = AsyncMock()
        settings = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            razorpay_key_id="rzp_test_id",
            razorpay_key_secret="rzp_test_secret",
            razorpay_webhook_secret="rzp_test_webhook_secret",
            app_secret_key="x" * 32,
            jwt_secret_key="y" * 32,
            capability_signing_key="z" * 16,
        )

        limiter = RateLimiter("api")

        with patch(
            "razorguard.interfaces.http.middleware.rate_limit.check_rate_limit",
            side_effect=RateLimitExceededError("test-scope"),
        ), pytest.raises(RateLimitExceededError):
            await limiter(request=request, redis=redis_mock, settings=settings)
