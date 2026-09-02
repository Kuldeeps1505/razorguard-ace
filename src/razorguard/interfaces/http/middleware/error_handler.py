"""
Global error handler.

Maps typed RazorGuard errors to HTTP responses with structured bodies.
Never leaks internal stack traces to clients in production.
Every error response has a machine-readable 'code' field.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.errors import (
    CapabilityExpiredError,
    CapabilityInvalidError,
    CapabilityReplayError,
    CapabilityRevokedError,
    ConcurrentExecutionError,
    ConsentExpiredError,
    ConsentRequiredError,
    DuplicatePaymentError,
    IntentExpiredError,
    IntentImmutableError,
    InvalidIntentError,
    InvalidWebhookError,
    MerchantUnavailableError,
    PaymentFailedError,
    PaymentUnknownError,
    PolicyDeniedError,
    PolicyUnavailableError,
    PriceChangedError,
    ProductUnavailableError,
    RateLimitExceededError,
    RazorGuardError,
    StubAdapterBlockedError,
    UnauthorizedAgentError,
)

logger = get_logger(__name__)


def _error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    # ── Domain errors → HTTP status mapping ──────────────────

    @app.exception_handler(InvalidIntentError)
    @app.exception_handler(IntentImmutableError)
    async def bad_request_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(UnauthorizedAgentError)
    async def unauthorized_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(StubAdapterBlockedError)
    @app.exception_handler(PolicyDeniedError)
    @app.exception_handler(PolicyUnavailableError)
    @app.exception_handler(CapabilityExpiredError)
    @app.exception_handler(CapabilityRevokedError)
    @app.exception_handler(CapabilityReplayError)
    @app.exception_handler(CapabilityInvalidError)
    @app.exception_handler(ConsentExpiredError)
    async def forbidden_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(IntentExpiredError)
    @app.exception_handler(ProductUnavailableError)
    @app.exception_handler(MerchantUnavailableError)
    async def not_found_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(DuplicatePaymentError)
    @app.exception_handler(ConcurrentExecutionError)
    async def conflict_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(ConsentRequiredError)
    async def consent_required_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(PriceChangedError)
    async def price_changed_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(PaymentUnknownError)
    async def unknown_payment_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        logger.warning("payment_unknown_state", **exc.details)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(PaymentFailedError)
    async def payment_failed_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(InvalidWebhookError)
    async def webhook_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        # Log security event — do not reveal reason to caller
        logger.warning("invalid_webhook_rejected", reason=exc.details.get("reason"))
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_body("INVALID_WEBHOOK", "Webhook rejected"),
        )

    @app.exception_handler(RazorGuardError)
    async def generic_razorguard_handler(request: Request, exc: RazorGuardError) -> JSONResponse:
        logger.error("unhandled_domain_error", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(exc.code, exc.message),
        )

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("INTERNAL_ERROR", "An unexpected error occurred"),
        )
