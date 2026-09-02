"""
Shared FastAPI dependencies.

All dependencies that cross multiple routes live here.
"""

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.cache.redis import get_redis
from razorguard.infrastructure.database.session import get_db_session
from razorguard.shared.config import Settings, get_settings

# Re-export commonly used dependency types
DBSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]  # type: ignore[type-arg]
AppSettings = Annotated[Settings, Depends(get_settings)]
