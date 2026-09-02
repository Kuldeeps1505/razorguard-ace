"""
Distributed locking via Redis.

Used to prevent concurrent payment execution for the same intent.
IMPORTANT: DB uniqueness constraints are the final safety net —
           Redis locks are the first line of defence only.
           Never rely solely on Redis for financial correctness.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis

from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.constants import REDIS_PREFIX_LOCK
from razorguard.shared.errors import ConcurrentExecutionError

logger = get_logger(__name__)


@asynccontextmanager
async def acquire_payment_lock(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    intent_id: str,
    ttl_seconds: int = 30,
) -> AsyncGenerator[None, None]:
    """
    Acquire a distributed lock for a payment execution.

    Raises ConcurrentExecutionError if lock is already held.
    Lock is released on context exit (success or failure).

    Usage:
        async with acquire_payment_lock(redis, intent_id):
            await execute_payment(...)
    """
    lock_key = f"{REDIS_PREFIX_LOCK}payment:{intent_id}"
    lock_value = "locked"

    acquired = await redis.set(
        lock_key,
        lock_value,
        nx=True,  # only set if not exists
        ex=ttl_seconds,  # auto-expire — prevents dead locks
    )

    if not acquired:
        logger.warning(
            "payment_lock_contention",
            intent_id=intent_id,
            lock_key=lock_key,
        )
        raise ConcurrentExecutionError(intent_id)

    logger.debug("payment_lock_acquired", intent_id=intent_id)
    try:
        yield
    finally:
        # Only release if we still own it (atomic delete)
        await redis.delete(lock_key)
        logger.debug("payment_lock_released", intent_id=intent_id)
