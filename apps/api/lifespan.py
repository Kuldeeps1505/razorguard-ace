"""
FastAPI lifespan — startup and shutdown events.

Validates critical dependencies on startup.
Fails fast rather than starting in a broken state.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from razorguard.infrastructure.cache.redis import ping_redis
from razorguard.infrastructure.database.session import get_engine
from razorguard.infrastructure.observability.logging import configure_logging, get_logger
from razorguard.shared.config import get_settings

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — runs startup checks, then yields, then cleans up."""
    settings = get_settings()

    # ── Configure logging first ───────────────────────────────
    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
    )

    logger.info(
        "razorguard_starting",
        env=settings.app_env,
        razorpay_mode=settings.razorpay_mode,
        llm_provider=settings.llm_provider,
    )

    # ── Validate Razorpay is in test mode ─────────────────────
    if settings.razorpay_mode == "live" and not settings.is_production:
        raise RuntimeError(
            "Razorpay live mode is not allowed outside production. "
            "Set RAZORPAY_MODE=test in your .env"
        )

    # ── Check database connection ─────────────────────────────
    try:
        engine = get_engine(settings)
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("database_connected")
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
        raise

    # ── Check Redis ───────────────────────────────────────────
    redis_ok = await ping_redis(settings)
    if not redis_ok:
        logger.error("redis_connection_failed")
        raise RuntimeError("Redis is unavailable — cannot start safely")
    logger.info("redis_connected")

    logger.info("razorguard_ready", host=settings.app_host, port=settings.app_port)

    yield  # ── Application runs ──────────────────────────────

    # ── Cleanup ───────────────────────────────────────────────
    logger.info("razorguard_shutting_down")
