"""
Integration tests — health endpoints.

Uses the FastAPI test client with mocked infrastructure dependencies.
Does not require real Postgres or Redis.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client_no_lifespan():
    """
    Client that skips lifespan startup (no real DB/Redis needed).
    Patches are applied before the app is imported into the transport.
    """
    with (
        patch(
            "razorguard.infrastructure.cache.redis.ping_redis",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "razorguard.infrastructure.database.session.get_engine",
        ) as mock_engine,
    ):
        # Mock the engine connect context manager
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.execute = AsyncMock()
        mock_engine.return_value.connect.return_value = mock_conn

        from apps.api.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c


@pytest.mark.asyncio
async def test_liveness(client_no_lifespan: AsyncClient):
    response = await client_no_lifespan.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_returns_json(client_no_lifespan: AsyncClient):
    with (
        patch(
            "razorguard.interfaces.http.routes.health.ping_redis",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "razorguard.interfaces.http.routes.health.get_session_factory",
        ) as mock_factory,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_factory.return_value.return_value = mock_session

        response = await client_no_lifespan.get("/health/ready")
        data = response.json()
        assert "status" in data
        assert "checks" in data


@pytest.mark.asyncio
async def test_request_id_header_present(client_no_lifespan: AsyncClient):
    """Every response must carry X-Request-ID for traceability."""
    response = await client_no_lifespan.get("/health/live")
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_request_id_propagated(client_no_lifespan: AsyncClient):
    """If client sends X-Request-ID, it must be echoed back."""
    response = await client_no_lifespan.get(
        "/health/live",
        headers={"X-Request-ID": "test-req-123"},
    )
    assert response.headers.get("x-request-id") == "test-req-123"
