"""
Shared pytest fixtures.

All tests use these fixtures. Phase-specific fixtures live
in their own conftest.py files in subdirectories.
"""

import os
from unittest.mock import AsyncMock

import pytest

# ── Force test environment before any imports touch config ────
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-32-chars-minimum-x")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://razorguard:razorguard@localhost:5432/razorguard_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_fixture")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "test_secret_fixture")
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "webhook_secret_fixture")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-32-chars-minimum-x")
os.environ.setdefault("CAPABILITY_SIGNING_KEY", "test-cap-key-16ch")
os.environ.setdefault("LOG_FORMAT", "console")
os.environ.setdefault("LOG_LEVEL", "DEBUG")


from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from razorguard.shared.config import Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Return test settings singleton."""
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client — does not require a real Redis."""
    redis = AsyncMock()
    redis.ping.return_value = True
    redis.set.return_value = True
    redis.get.return_value = None
    redis.delete.return_value = 1
    redis.eval.return_value = 1
    return redis


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock DB session — does not require a real database."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
async def app() -> FastAPI:
    """
    Return the FastAPI app with mocked dependencies.
    Does not start a real server or connect to real services.
    """
    from apps.api.main import app as _app

    return _app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    """Async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
