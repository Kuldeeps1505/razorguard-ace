"""
Request-level idempotency via Redis.

Ensures duplicate API requests return the cached response
instead of triggering a second payment execution.

Multiple idempotency layers exist in RazorGuard:
  1. Request idempotency key (this module)
  2. Intent execution uniqueness (DB constraint)
  3. Distributed lock (locks.py)
  4. Razorpay idempotency key (payment executor)
  5. Webhook event ID uniqueness (webhook handler)
"""

import json
from typing import Any

import redis.asyncio as aioredis

from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.constants import REDIS_PREFIX_IDEMPOTENCY

logger = get_logger(__name__)

_DEFAULT_TTL = 86_400  # 24 hours


async def get_cached_response(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    idempotency_key: str,
) -> dict[str, Any] | None:
    """Return cached response for this key, or None if not found."""
    cache_key = f"{REDIS_PREFIX_IDEMPOTENCY}{idempotency_key}"
    raw = await redis.get(cache_key)
    if raw:
        logger.info("idempotency_cache_hit", idempotency_key=idempotency_key)
        return json.loads(raw)
    return None


async def cache_response(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    idempotency_key: str,
    response: dict[str, Any],
    ttl: int = _DEFAULT_TTL,
) -> None:
    """Store response under this idempotency key."""
    cache_key = f"{REDIS_PREFIX_IDEMPOTENCY}{idempotency_key}"
    await redis.set(cache_key, json.dumps(response), ex=ttl)
    logger.debug("idempotency_response_cached", idempotency_key=idempotency_key)
