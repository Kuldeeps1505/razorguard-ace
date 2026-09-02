"""
Webhook HTTP route.

POST /webhooks/razorpay

Security pipeline (order matters):
  1. Read raw body bytes (before Pydantic parsing)
  2. Read Razorpay-Signature header
  3. Verify signature (raises 400 if invalid — never reveal reason)
  4. Parse JSON
  5. Extract event ID for deduplication
  6. Process event
"""

import json
from typing import Annotated

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse

from razorguard.application.webhooks.process_webhook import process_webhook
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.payments.webhook_verifier import verify_webhook_signature
from razorguard.shared.errors import InvalidWebhookError

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/razorpay",
    status_code=status.HTTP_200_OK,
    summary="Razorpay webhook receiver",
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """
    Receive and process Razorpay webhook events.

    Always returns 200 to Razorpay (even on duplicates) to prevent retries.
    Security events are logged but not exposed in the response.
    """
    # 1. Read raw bytes — MUST happen before any parsing
    raw_body = await request.body()

    # 2. Signature check — reject unsigned/forged webhooks immediately
    if not x_razorpay_signature:
        logger.warning("webhook_missing_signature")
        raise InvalidWebhookError("Missing signature header")

    verify_webhook_signature(
        payload_body=raw_body,
        signature=x_razorpay_signature,
    )

    # 3. Parse payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as err:
        raise InvalidWebhookError("Invalid JSON payload") from err

    event_type = payload.get("event", "unknown")
    razorpay_event_id = payload.get("id") or payload.get("event_id", "")

    if not razorpay_event_id:
        logger.warning("webhook_missing_event_id", event_type=event_type)
        raise InvalidWebhookError("Missing event ID")

    # 4. Process (uses DB session — get it here to avoid dependency injection complexity)
    from razorguard.infrastructure.database.session import get_session_factory
    from razorguard.shared.config import get_settings

    settings = get_settings()
    factory = get_session_factory(settings)

    async with factory() as session:
        try:
            result = await process_webhook(
                razorpay_event_id=razorpay_event_id,
                event_type=event_type,
                raw_payload=payload,
                session=session,
            )
            await session.commit()
            return JSONResponse(content={"status": "ok", "result": result})
        except Exception as exc:
            # The verified event record is a durable inbox item. Preserve it
            # for retry rather than discarding provider evidence.
            await session.rollback()
            try:
                import uuid

                from razorguard.infrastructure.database.models.webhook_event import WebhookEvent
                from razorguard.shared.security import generate_id
                async with factory() as recovery_session:
                    recovery_session.add(WebhookEvent(id=uuid.UUID(generate_id()), razorpay_event_id=razorpay_event_id,
                        event_type=event_type, raw_payload=json.dumps(payload), signature_verified=True,
                        processing_status="FAILED", error_detail=str(exc)[:1000]))
                    await recovery_session.commit()
            except Exception:
                logger.exception("webhook_inbox_persist_failed", event_id=razorpay_event_id)
            logger.error(
                "webhook_processing_error",
                event_id=razorpay_event_id,
                error=str(exc),
            )
            # Return 200 to prevent Razorpay retries — event is logged for investigation
            return JSONResponse(
                content={"status": "error", "message": "Processing failed — logged"}
            )
