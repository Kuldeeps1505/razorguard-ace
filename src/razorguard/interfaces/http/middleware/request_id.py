"""
Request ID middleware.

Generates or propagates a unique request ID for every HTTP request.
Binds it to the correlation context so it appears in all log lines.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from razorguard.infrastructure.observability.correlation import (
    clear_context,
    set_request_context,
)
from razorguard.shared.constants import HEADER_CORRELATION_ID, HEADER_REQUEST_ID


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        # Accept incoming request ID (from upstream / load balancer) or generate one
        request_id = (
            request.headers.get(HEADER_REQUEST_ID)
            or request.headers.get(HEADER_CORRELATION_ID)
            or str(uuid.uuid4())
        )

        set_request_context(request_id=request_id)

        try:
            response = await call_next(request)
        finally:
            clear_context()

        response.headers[HEADER_REQUEST_ID] = request_id
        return response
