"""
Health check endpoints.

/health/live   — liveness  (is the process running?)
/health/ready  — readiness (are dependencies reachable?)

Used by Docker health checks and load balancers.
"""

from typing import Annotated

import sqlalchemy
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from razorguard.infrastructure.cache.redis import ping_redis
from razorguard.infrastructure.database.session import get_session_factory
from razorguard.shared.config import Settings, get_settings

router = APIRouter()


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness() -> dict:
    """Process is alive."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    """
    All critical dependencies are reachable.
    Returns 200 if ready, 503 if not.
    """
    checks: dict[str, bool] = {}

    # Check Redis
    checks["redis"] = await ping_redis(settings)

    # Check Database
    try:
        factory = get_session_factory(settings)
        async with factory() as session:
            await session.execute(sqlalchemy.text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    all_ok = all(checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )
