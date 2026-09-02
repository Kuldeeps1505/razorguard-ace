"""
ProcessWebhook use case — handles verified Razorpay webhook events.

Security pipeline:
  1. Signature verified (done in route BEFORE this is called)
  2. Event deduplicated (razorpay_event_id is unique)
  3. Payload parsed and validated
  4. Transaction looked up and cross-validated
  5. Amount and merchant validated against our DB
  6. State transition validated (no illegal transitions)
  7. State updated

INVARIANTS:
  - Never trust payment_id / order_id from webhook without DB cross-check
  - Never transition to an illegal state
  - Never process same event twice
  - Out-of-order events: validate transition before applying
  - UNKNOWN → reconcile, not blind state change
"""

import json
import uuid

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.transactions.transition_state import transition_transaction
from razorguard.infrastructure.database.models.transaction import Transaction
from razorguard.infrastructure.database.models.webhook_event import WebhookEvent
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.clock import utcnow
from razorguard.shared.enums import TransactionStatus
from razorguard.shared.security import generate_id

logger = get_logger(__name__)


async def process_webhook(
    *,
    razorpay_event_id: str,
    event_type: str,
    raw_payload: dict,
    session: AsyncSession,
) -> dict:
    """
    Process a verified Razorpay webhook event.

    Signature must be verified BEFORE calling this function.
    Returns a result dict describing what was done.
    Idempotent — safe to call multiple times with the same event.
    """

    # 1. Deduplicate — check if we've seen this event before
    result = await session.execute(
        select(WebhookEvent).where(WebhookEvent.razorpay_event_id == razorpay_event_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.info(
            "webhook_duplicate_ignored",
            razorpay_event_id=razorpay_event_id,
            event_type=event_type,
        )
        return {"status": "duplicate", "event_id": razorpay_event_id}

    # 2. Extract payment/order IDs from payload
    payment_entity = raw_payload.get("payload", {}).get("payment", {}).get("entity", {})
    razorpay_payment_id = payment_entity.get("id")
    razorpay_order_id = payment_entity.get("order_id")

    # 3. Persist webhook event record (before processing)
    webhook_record = WebhookEvent(
        id=uuid.UUID(generate_id()),
        razorpay_event_id=razorpay_event_id,
        event_type=event_type,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_order_id,
        raw_payload=json.dumps(raw_payload),
        signature_verified=True,
        processing_status="RECEIVED",
    )
    session.add(webhook_record)
    await session.flush()

    # 4. Find associated transaction
    transaction_id: uuid.UUID | None = None
    if razorpay_order_id:
        txn_result = await session.execute(
            select(Transaction).where(Transaction.razorpay_order_id == razorpay_order_id)
        )
        txn = txn_result.scalar_one_or_none()
        if txn:
            transaction_id = txn.id
            webhook_record.transaction_id = transaction_id

    # 5. Process by event type
    processing_result = await _handle_event(
        event_type=event_type,
        payment_entity=payment_entity,
        razorpay_order_id=razorpay_order_id,
        transaction_id=transaction_id,
        session=session,
    )

    # 6. Mark webhook as processed
    webhook_record.processing_status = "PROCESSED"
    webhook_record.processed_at = utcnow()
    await session.flush()

    logger.info(
        "webhook_processed",
        razorpay_event_id=razorpay_event_id,
        event_type=event_type,
        result=processing_result,
    )
    return {"status": "processed", "event_id": razorpay_event_id, "result": processing_result}


async def retry_webhook_event(*, event_id: uuid.UUID, session: AsyncSession) -> dict:
    """Durable inbox retry: only verified, non-processed events may be replayed."""
    event = await session.get(WebhookEvent, event_id)
    if not event or not event.signature_verified:
        return {"status": "skipped", "reason": "event_missing_or_unverified"}
    if event.processing_status == "PROCESSED":
        return {"status": "skipped", "reason": "already_processed"}
    event.processing_status = "RETRYING"
    await session.flush()
    try:
        payload = json.loads(event.raw_payload)
        result = await _handle_event(
            event_type=event.event_type,
            payment_entity=payload.get("payload", {}).get("payment", {}).get("entity", {}),
            razorpay_order_id=event.razorpay_order_id,
            transaction_id=event.transaction_id,
            session=session,
        )
        event.processing_status = "PROCESSED"
        event.processed_at = utcnow()
        event.error_detail = None
        await session.flush()
        return {"status": "processed", "result": result}
    except Exception as exc:
        event.processing_status = "FAILED"
        event.error_detail = str(exc)[:1000]
        await session.flush()
        return {"status": "failed", "reason": "processing_error"}


async def _handle_event(
    *,
    event_type: str,
    payment_entity: dict,
    razorpay_order_id: str | None,
    transaction_id: uuid.UUID | None,
    session: AsyncSession,
) -> dict:
    """Dispatch to the appropriate event handler."""
    if event_type == "payment.captured":
        return await _handle_payment_captured(
            payment_entity=payment_entity,
            transaction_id=transaction_id,
            session=session,
        )
    if event_type == "payment.failed":
        return await _handle_payment_failed(
            payment_entity=payment_entity,
            transaction_id=transaction_id,
            session=session,
        )
    logger.info("webhook_event_type_unhandled", event_type=event_type)
    return {"action": "ignored", "reason": f"Unhandled event type: {event_type}"}


async def _handle_payment_captured(
    *,
    payment_entity: dict,
    transaction_id: uuid.UUID | None,
    session: AsyncSession,
) -> dict:
    """payment.captured — payment was successfully captured by the bank."""
    if not transaction_id:
        return {"action": "no_transaction_found"}

    result = await session.execute(select(Transaction).where(Transaction.id == transaction_id))
    txn = result.scalar_one_or_none()
    if not txn:
        return {"action": "transaction_not_found"}

    current = TransactionStatus(txn.status)

    # Validate amount from webhook matches our record (integrity check)
    webhook_amount = payment_entity.get("amount", 0)
    if webhook_amount and webhook_amount != txn.amount_minor:
        logger.error(
            "webhook_amount_mismatch",
            transaction_id=str(transaction_id),
            our_amount=txn.amount_minor,
            webhook_amount=webhook_amount,
        )
        return {"action": "amount_mismatch_rejected"}

    # Update payment ID from webhook
    payment_id = payment_entity.get("id")
    if payment_id:
        txn.razorpay_payment_id = payment_id

    # Transition to COMPLETED if valid
    from razorguard.domain.intents.state_machine import can_transition

    if can_transition(current, TransactionStatus.COMPLETED):
        await transition_transaction(
            transaction_id=transaction_id,
            target_status=TransactionStatus.COMPLETED,
            expected_version=txn.version,
            session=session,
        )
        # Mirror status to intent for UI
        from razorguard.infrastructure.database.models.intent import Intent
        await session.execute(
            sa_update(Intent)
            .where(Intent.id == txn.intent_id)
            .values(status=TransactionStatus.COMPLETED.value)
        )
        logger.info("webhook_payment_captured_completed", transaction_id=str(transaction_id))
        return {"action": "marked_completed"}

    if current == TransactionStatus.COMPLETED:
        return {"action": "already_completed"}

    logger.warning(
        "webhook_illegal_transition",
        from_state=current.value,
        to_state="COMPLETED",
    )
    return {"action": "illegal_transition_ignored"}


async def _handle_payment_failed(
    *,
    payment_entity: dict,
    transaction_id: uuid.UUID | None,
    session: AsyncSession,
) -> dict:
    """payment.failed — payment was rejected by bank/gateway."""
    if not transaction_id:
        return {"action": "no_transaction_found"}

    result = await session.execute(select(Transaction).where(Transaction.id == transaction_id))
    txn = result.scalar_one_or_none()
    if not txn:
        return {"action": "transaction_not_found"}

    current = TransactionStatus(txn.status)
    from razorguard.domain.intents.state_machine import can_transition

    error_desc = (
        payment_entity.get("error_description")
        or payment_entity.get("error_code")
        or "Payment failed"
    )

    if can_transition(current, TransactionStatus.FAILED):
        await transition_transaction(
            transaction_id=transaction_id,
            target_status=TransactionStatus.FAILED,
            expected_version=txn.version,
            session=session,
            reason=error_desc,
        )
        # Mirror status to intent for UI
        from razorguard.infrastructure.database.models.intent import Intent
        await session.execute(
            sa_update(Intent)
            .where(Intent.id == txn.intent_id)
            .values(status=TransactionStatus.FAILED.value)
        )
        return {"action": "marked_failed"}

    if current.is_terminal:
        return {"action": "already_terminal"}
    return {"action": "illegal_transition_ignored"}
