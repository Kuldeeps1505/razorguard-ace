"""
ReconcileUnknown — resolve UNKNOWN payment states by querying Razorpay.

CRITICAL RULE: UNKNOWN ≠ FAILED. Never treat them the same.
UNKNOWN means: outcome uncertain due to network/timeout.
Reconciliation queries Razorpay to find the real outcome.

Flow:
  UNKNOWN → query Razorpay order/payment status
          → if captured:  VERIFYING → COMPLETED
          → if failed:    VERIFYING → FAILED
          → if pending:   stay UNKNOWN, retry later
          → if not found: stay UNKNOWN, alert

NEVER blindly retry the payment. Only query.

This runs as a background Celery task (Phase 10).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.transactions.transition_state import transition_transaction
from razorguard.infrastructure.database.models.reconciliation import ReconciliationJob
from razorguard.infrastructure.database.models.transaction import Transaction
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.observability.metrics import (
    payments_reconciled,
    reconciliation_queue_depth,
)
from razorguard.infrastructure.payments.razorpay_client import (
    fetch_payments_for_order,
)
from razorguard.shared.clock import utcnow, utcnow_plus
from razorguard.shared.enums import TransactionStatus
from razorguard.shared.security import generate_id

logger = get_logger(__name__)

MAX_RECONCILIATION_ATTEMPTS = 10
RETRY_BACKOFF_SECONDS = [30, 60, 120, 300, 600, 1800, 3600, 7200, 14400, 28800]


async def reconcile_unknown_payment(
    *,
    transaction_id: uuid.UUID,
    session: AsyncSession,
) -> dict:
    """
    Query Razorpay to resolve an UNKNOWN payment.
    Returns a dict describing what happened.

    NEVER creates a new payment — only queries existing one.
    """
    # Fetch transaction
    result = await session.execute(select(Transaction).where(Transaction.id == transaction_id))
    txn = result.scalar_one_or_none()
    if not txn:
        logger.error("reconcile_transaction_not_found", transaction_id=str(transaction_id))
        return {"status": "error", "reason": "transaction_not_found"}

    current = TransactionStatus(txn.status)
    if current not in (TransactionStatus.UNKNOWN, TransactionStatus.SUBMITTED):
        logger.info(
            "reconcile_not_needed",
            transaction_id=str(transaction_id),
            status=current.value,
        )
        return {"status": "skipped", "reason": f"status is {current.value}"}

    if not txn.razorpay_order_id:
        logger.warning(
            "reconcile_no_order_id",
            transaction_id=str(transaction_id),
        )
        return {"status": "error", "reason": "no_razorpay_order_id"}

    # Fetch or create reconciliation job
    job = await _get_or_create_job(txn.id, session)
    if job.attempt_count >= job.max_attempts:
        logger.error(
            "reconcile_max_attempts_exceeded",
            transaction_id=str(transaction_id),
            attempts=job.attempt_count,
        )
        return {"status": "abandoned", "reason": "max_attempts_exceeded"}

    # Increment attempt counter
    job.attempt_count += 1
    await session.flush()

    # Query Razorpay — this is a READ, not a new payment
    try:
        payments = fetch_payments_for_order(txn.razorpay_order_id)
    except Exception as exc:
        logger.warning(
            "reconcile_razorpay_query_failed",
            transaction_id=str(transaction_id),
            error=str(exc),
        )
        backoff = RETRY_BACKOFF_SECONDS[min(job.attempt_count - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
        job.next_attempt_at = utcnow_plus(seconds=backoff)
        await session.flush()
        return {"status": "retry", "reason": "razorpay_query_failed"}

    # Analyze payment statuses
    captured = [p for p in payments if p.get("status") == "captured"]
    failed = [p for p in payments if p.get("status") == "failed"]

    if captured:
        payment_id = captured[0].get("id")
        txn.razorpay_payment_id = payment_id

        # UNKNOWN → VERIFYING → COMPLETED
        txn = await transition_transaction(
            transaction_id=transaction_id,
            target_status=TransactionStatus.VERIFYING,
            expected_version=txn.version,
            session=session,
        )
        txn = await transition_transaction(
            transaction_id=transaction_id,
            target_status=TransactionStatus.COMPLETED,
            expected_version=txn.version,
            session=session,
        )
        _mark_job_resolved(job, "COMPLETED")
        await session.flush()
        payments_reconciled.labels(outcome="completed").inc()
        logger.info(
            "reconcile_resolved_completed",
            transaction_id=str(transaction_id),
            payment_id=payment_id,
        )
        return {"status": "resolved", "outcome": "completed", "payment_id": payment_id}

    if failed:
        error_desc = failed[0].get("error_description", "Payment failed")
        txn = await transition_transaction(
            transaction_id=transaction_id,
            target_status=TransactionStatus.VERIFYING,
            expected_version=txn.version,
            session=session,
        )
        txn = await transition_transaction(
            transaction_id=transaction_id,
            target_status=TransactionStatus.FAILED,
            expected_version=txn.version,
            session=session,
            reason=error_desc,
        )
        _mark_job_resolved(job, "FAILED")
        await session.flush()
        payments_reconciled.labels(outcome="failed").inc()
        logger.info(
            "reconcile_resolved_failed",
            transaction_id=str(transaction_id),
        )
        return {"status": "resolved", "outcome": "failed"}

    # Still pending — retry later
    backoff = RETRY_BACKOFF_SECONDS[min(job.attempt_count - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
    job.next_attempt_at = utcnow_plus(seconds=backoff)
    await session.flush()
    logger.info(
        "reconcile_still_pending",
        transaction_id=str(transaction_id),
        attempt=job.attempt_count,
        next_retry_seconds=backoff,
    )
    return {"status": "pending", "next_retry_seconds": backoff}


async def _get_or_create_job(
    transaction_id: uuid.UUID,
    session: AsyncSession,
) -> ReconciliationJob:
    result = await session.execute(
        select(ReconciliationJob).where(
            ReconciliationJob.transaction_id == transaction_id,
            ReconciliationJob.status == "PENDING",
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    job = ReconciliationJob(
        id=uuid.UUID(generate_id()),
        transaction_id=transaction_id,
        status="PENDING",
        attempt_count=0,
        max_attempts=MAX_RECONCILIATION_ATTEMPTS,
    )
    session.add(job)
    await session.flush()
    reconciliation_queue_depth.inc()
    return job


def _mark_job_resolved(job: ReconciliationJob, outcome: str) -> None:
    job.status = "RESOLVED"
    job.resolved_status = outcome
    job.resolved_at = utcnow()
    reconciliation_queue_depth.dec()
