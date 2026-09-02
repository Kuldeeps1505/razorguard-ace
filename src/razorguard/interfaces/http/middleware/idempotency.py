"""
Idempotency Middleware.

Prevents duplicate state mutations from retried HTTP requests.

HOW IT WORKS:
  1. Client sends a mutating request (POST) with an `Idempotency-Key` header.
  2. Middleware checks Redis for a cached response keyed by (method + path + key).
  3. If found → return the cached response immediately (no DB hit).
  4. If not found → process the request, cache the response for 24 hours, return it.

SECURITY:
  - Keys are scoped per HTTP method + path to prevent cross-endpoint replay.
  - Only POST/PATCH/PUT endpoints are subject to idempotency (GET is naturally safe).
  - Keys are stored with a 24-hour TTL — after that, the same key can be reused.

USAGE:
  Clients send:  Idempotency-Key: <uuid4>
  If header is missing, the request proceeds without idempotency guarantee.
"""

import json
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_IDEMPOTENCY_TTL_SECONDS = 86_400  # 24 hours
_PROTECTED_METHODS = {"POST", "PUT", "PATCH"}
_IDEMPOTENCY_HEADER = "idempotency-key"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed idempotency layer for mutating HTTP endpoints.

    Attach to the FastAPI app via app.add_middleware(IdempotencyMiddleware).
    Requires Redis to be accessible — falls through gracefully if Redis is down.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only apply to mutating methods
        if request.method not in _PROTECTED_METHODS:
            return await call_next(request)

        idempotency_key = request.headers.get(_IDEMPOTENCY_HEADER)
        if not idempotency_key:
            # No key provided — proceed without idempotency guarantee
            return await call_next(request)

        # Build a cache key scoped to (method, path, idempotency_key)
        cache_key = f"idempotency:{request.method}:{request.url.path}:{idempotency_key}"

        try:
            from razorguard.infrastructure.cache.redis import get_redis_direct
            redis = await get_redis_direct()

            # Check for a cached response
            cached = await redis.get(cache_key)
            if cached:
                logger.info(
                    "idempotency_cache_hit",
                    extra={"idempotency_key": idempotency_key, "path": request.url.path},
                )
                data = json.loads(cached)
                return JSONResponse(
                    content=data["body"],
                    status_code=data["status_code"],
                    headers={"X-Idempotency-Replayed": "true"},
                )

            # Process the request
            response = await call_next(request)

            # Only cache successful responses
            if 200 <= response.status_code < 300:
                body_bytes = b""
                async for chunk in response.body_iterator:
                    body_bytes += chunk

                try:
                    body_json = json.loads(body_bytes)
                    cache_payload = json.dumps(
                        {"status_code": response.status_code, "body": body_json}
                    )
                    await redis.setex(cache_key, _IDEMPOTENCY_TTL_SECONDS, cache_payload)
                    logger.info(
                        "idempotency_response_cached",
                        extra={"idempotency_key": idempotency_key, "path": request.url.path},
                    )
                except Exception:
                    pass  # Non-JSON body — skip caching

                return Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

            return response

        except Exception as exc:
            # If Redis is unavailable, fall through without idempotency
            logger.warning(
                "idempotency_redis_unavailable",
                extra={"error": str(exc)},
            )
            return await call_next(request)
