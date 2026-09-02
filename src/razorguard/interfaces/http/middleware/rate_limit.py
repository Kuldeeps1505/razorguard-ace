"""
Rate limiting dependency for FastAPI routes.
"""

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Request

from razorguard.infrastructure.cache.rate_limiter import check_rate_limit
from razorguard.infrastructure.cache.redis import get_redis
from razorguard.shared.config import Settings, get_settings


class RateLimiter:
    """
    FastAPI dependency for sliding-window rate limiting.
    """

    def __init__(self, scope: str):
        self.scope = scope

    async def __call__(
        self,
        request: Request,
        redis: Annotated[aioredis.Redis, Depends(get_redis)],  # type: ignore[type-arg]
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        # In testing environment, if redis is not configured, bypass
        if settings.is_testing and not redis:
            return

        # Determine limit based on scope and settings
        if self.scope == "api":
            limit = settings.rate_limit_api_per_minute
        elif self.scope == "payment":
            limit = settings.rate_limit_payment_per_minute
        elif self.scope == "agent":
            limit = settings.rate_limit_agent_per_minute
        else:
            limit = 60

        # Resolve identifier: state.user_id (if authenticated) -> client IP
        client_ip = request.client.host if request.client else "unknown_ip"
        user_id = getattr(request.state, "user_id", None)
        identifier = str(user_id) if user_id else client_ip

        await check_rate_limit(
            redis=redis,
            scope=self.scope,
            identifier=identifier,
            limit=limit,
            window_seconds=60,
        )
