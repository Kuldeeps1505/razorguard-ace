"""
Celery task definitions.

Tasks are stubs for Phase 1 — fully implemented in Phases 10 and 9.

IMPORTANT: Every task must be idempotent.
           Workers may execute a task more than once.
           Always check current state before acting.
"""

from apps.worker.main import celery_app
from razorguard.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(
    name="apps.worker.tasks.reconcile_unknown_payment",
    bind=True,
    max_retries=5,
    default_retry_delay=60,  # seconds
)
def reconcile_unknown_payment(self, transaction_id: str) -> dict:  # type: ignore[override]
    """
    Resolve a payment in UNKNOWN state.

    Queries Razorpay for the actual payment status.
    NEVER triggers a new payment — only queries existing one.
    """
    import asyncio
    import uuid as _uuid

    from razorguard.application.reconciliation.reconcile_unknown import (
        reconcile_unknown_payment as _reconcile,
    )
    from razorguard.infrastructure.database.session import get_session_factory
    from razorguard.shared.config import get_settings

    logger.info("reconcile_unknown_payment_started", transaction_id=transaction_id)

    async def _run() -> dict:
        settings = get_settings()
        factory = get_session_factory(settings)
        async with factory() as session:
            result = await _reconcile(
                transaction_id=_uuid.UUID(transaction_id),
                session=session,
            )
            await session.commit()
            return result

    return asyncio.run(_run())


@celery_app.task(
    name="apps.worker.tasks.process_webhook_event",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_webhook_event(self, event_id: str, payload: dict) -> dict:  # type: ignore[override]
    """
    Process a verified Razorpay webhook event.

    Handler is idempotent — duplicate events are safely ignored.

    Implemented fully in Phase 9.
    """
    import asyncio
    import uuid as _uuid

    from razorguard.application.webhooks.process_webhook import retry_webhook_event
    from razorguard.infrastructure.database.session import get_session_factory
    from razorguard.shared.config import get_settings
    async def _run() -> dict:
        factory = get_session_factory(get_settings())
        async with factory() as session:
            result = await retry_webhook_event(event_id=_uuid.UUID(event_id), session=session)
            await session.commit()
            return result
    return asyncio.run(_run())


@celery_app.task(name="apps.worker.tasks.release_expired_campaign_reservations")
def release_expired_campaign_reservations() -> dict:
    """Periodic janitor for abandoned offer holds."""
    import asyncio

    from razorguard.application.commerce.campaigns import (
        release_expired_campaign_reservations as release,
    )
    from razorguard.infrastructure.database.session import get_session_factory
    from razorguard.shared.config import get_settings
    async def _run() -> dict:
        factory = get_session_factory(get_settings())
        async with factory() as session:
            released = await release(session=session)
            await session.commit()
            return {"released": released}
    return asyncio.run(_run())


@celery_app.task(
    name="apps.worker.tasks.execute_checkout_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def execute_checkout_task(
    self,
    intent_id: str,
    user_id: str,
    agent_id: str,
    request_id: str,
    session_id: str,
) -> dict:
    """
    Execute the checkout pipeline asynchronously.
    """
    import asyncio
    import uuid as _uuid
    from razorguard.application.payments.checkout_handoff import checkout_and_pay
    from razorguard.infrastructure.database.session import get_session_factory
    from razorguard.infrastructure.cache.redis import get_redis
    from razorguard.shared.config import get_settings

    logger.info("execute_checkout_task_started", intent_id=intent_id)

    async def _run() -> dict:
        settings = get_settings()
        factory = get_session_factory(settings)
        # Manually create a redis client for the task
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(settings.redis_url)

        async with factory() as session:
            try:
                result = await checkout_and_pay(
                    intent_id=_uuid.UUID(intent_id),
                    authenticated_user_id=_uuid.UUID(user_id),
                    authenticated_agent_id=_uuid.UUID(agent_id),
                    request_id=request_id,
                    session_id=session_id,
                    session=session,
                    redis=redis_client,
                )
                await session.commit()
                return result
            finally:
                await redis_client.aclose()

    return asyncio.run(_run())


@celery_app.task(name="apps.worker.tasks.sweep_unknown_payments")
def sweep_unknown_payments() -> dict:
    """
    Periodic reconciliation sweeper.

    Finds all transactions stuck in UNKNOWN state and dispatches
    reconcile_unknown_payment for each one. Runs every 5 minutes via Beat.
    """
    import asyncio
    from sqlalchemy import select as sa_select
    from razorguard.infrastructure.database.session import get_session_factory
    from razorguard.infrastructure.database.models.transaction import Transaction
    from razorguard.shared.config import get_settings
    from razorguard.shared.enums import TransactionStatus

    logger.info("sweep_unknown_payments_started")

    async def _find_unknowns() -> list[str]:
        settings = get_settings()
        factory = get_session_factory(settings)
        async with factory() as session:
            result = await session.execute(
                sa_select(Transaction.id).where(
                    Transaction.status == TransactionStatus.UNKNOWN.value
                )
            )
            return [str(row[0]) for row in result.fetchall()]

    unknown_ids = asyncio.run(_find_unknowns())
    dispatched = 0
    for txn_id in unknown_ids:
        reconcile_unknown_payment.delay(txn_id)
        dispatched += 1

    logger.info("sweep_unknown_payments_completed", dispatched=dispatched)
    return {"dispatched": dispatched, "transaction_ids": unknown_ids}
