"""
Token-bucket rate limiter using Redis.

Applied at multiple levels: IP, user, agent, payment, tool.
Rate limits are configurable — never hardcoded.
"""

import redis.asyncio as aioredis

from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.constants import REDIS_PREFIX_RATE_LIMIT
from razorguard.shared.errors import RateLimitExceededError

logger = get_logger(__name__)

# Lua script: atomic sliding-window counter
_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - window * 1000)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, window)
    return 1
else
    return 0
end
"""


async def check_rate_limit(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    scope: str,
    identifier: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    """
    Check and increment rate limit counter.

    Raises RateLimitExceededError if limit is exceeded.

    Args:
        scope:          e.g. "api", "payment", "agent_tool"
        identifier:     e.g. user_id, agent_id, IP address
        limit:          max requests in window
        window_seconds: sliding window duration
    """
    import time

    key = f"{REDIS_PREFIX_RATE_LIMIT}{scope}:{identifier}"
    now_ms = int(time.time() * 1000)

    allowed = await redis.eval(
        _RATE_LIMIT_SCRIPT,
        1,
        key,
        window_seconds,
        limit,
        now_ms,
    )

    if not allowed:
        logger.warning(
            "rate_limit_exceeded",
            scope=scope,
            identifier=identifier,
            limit=limit,
            window_seconds=window_seconds,
        )
        raise RateLimitExceededError(f"{scope}:{identifier}")
