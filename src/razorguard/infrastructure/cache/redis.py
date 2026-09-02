"""
Redis connection pool.

Redis is used for: distributed locks, rate limiting, idempotency cache.
Redis is NEVER the sole source of financial correctness — DB is authoritative.
If Redis is unavailable for a money operation, fail closed.
"""

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends

from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.config import Settings, get_settings

logger = get_logger(__name__)

_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


def get_redis_client(settings: Settings) -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_client


async def get_redis(
    settings: Annotated[Settings, Depends(get_settings)],
) -> aioredis.Redis:  # type: ignore[type-arg]
    """FastAPI dependency: yields a Redis client."""
    return get_redis_client(settings)


async def ping_redis(settings: Settings) -> bool:
    """Health check — returns False if Redis is unreachable."""
    try:
        client = get_redis_client(settings)
        await client.ping()
        return True
    except Exception as e:
        logger.warning("redis_unavailable", error=str(e))
        return False


async def get_redis_direct() -> aioredis.Redis:  # type: ignore[type-arg]
    """
    Direct Redis client without FastAPI DI — for use in middleware.

    Falls back to creating a new client from settings if pool isn't initialised yet.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = get_redis_client(settings)
    return _redis_client
