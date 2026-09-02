"""
TransitionState use case — applies a validated state transition to a transaction.

Enforces:
1. Legal transition (via state machine)
2. Optimistic locking (version field prevents stale-worker execution)
3. Terminal state immutability (terminal → any = BLOCKED)
4. Audit event emitted on every transition

SECURITY:
- Only legal transitions are persisted
- Terminal states cannot be modified
- version field prevents concurrent worker execution
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.audit.record_event import record_audit_event
from razorguard.domain.intents.state_machine import validate_transition
from razorguard.infrastructure.database.models.transaction import Transaction
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.clock import utcnow
from razorguard.shared.enums import AuditActor, TransactionStatus
from razorguard.shared.errors import RazorGuardError

logger = get_logger(__name__)


class StaleTransactionError(RazorGuardError):
    def __init__(self, transaction_id: str) -> None:
        super().__init__(
            message=(
                f"Stale transaction version for {transaction_id}"
                " — concurrent modification detected"
            ),
            code="STALE_TRANSACTION",
            details={"transaction_id": transaction_id},
        )


async def transition_transaction(
    *,
    transaction_id: uuid.UUID,
    target_status: TransactionStatus,
    expected_version: int,
    session: AsyncSession,
    reason: str | None = None,
) -> Transaction:
    """
    Apply a state transition with optimistic locking.

    expected_version must match the current DB version.
    If it doesn't, another worker has modified the transaction → StaleTransactionError.
    """
    result = await session.execute(select(Transaction).where(Transaction.id == transaction_id))
    txn = result.scalar_one_or_none()
    if not txn:
        raise RazorGuardError(
            message=f"Transaction {transaction_id} not found",
            code="TRANSACTION_NOT_FOUND",
        )

    # Optimistic lock check
    if txn.version != expected_version:
        logger.warning(
            "stale_transaction_version",
            transaction_id=str(transaction_id),
            expected=expected_version,
            actual=txn.version,
        )
        raise StaleTransactionError(str(transaction_id))

    current_status = TransactionStatus(txn.status)

    # Validate transition (raises IllegalTransitionError if invalid)
    validate_transition(current_status, target_status)

    # Apply transition
    now = utcnow()
    txn.status = target_status
    txn.version = txn.version + 1  # increment for next optimistic lock

    # Set relevant timestamps
    if target_status == TransactionStatus.AUTHORIZED:
        txn.authorized_at = now
    elif target_status == TransactionStatus.EXECUTING:
        txn.submitted_at = now
    elif target_status == TransactionStatus.COMPLETED:
        txn.completed_at = now
    elif target_status in (TransactionStatus.FAILED, TransactionStatus.POLICY_BLOCKED):
        txn.failed_at = now
        if reason:
            txn.failure_reason = reason

    await session.flush()
    if target_status in (TransactionStatus.COMPLETED, TransactionStatus.FAILED,
                         TransactionStatus.EXPIRED, TransactionStatus.CANCELLED,
                         TransactionStatus.AGENT_STOPPED):
        from razorguard.application.commerce.budget import settle_budget_for_intent
        await settle_budget_for_intent(intent_id=txn.intent_id, status=target_status.value, session=session)
        from razorguard.application.commerce.campaigns import settle_campaign_for_intent
        await settle_campaign_for_intent(intent_id=txn.intent_id, captured=target_status == TransactionStatus.COMPLETED, session=session)
    await record_audit_event(
        session=session, request_id=f"transaction:{txn.id}:{txn.version}", actor=AuditActor.SYSTEM,
        action="transaction.state_changed", result=target_status.value, transaction_id=txn.id,
        intent_id=txn.intent_id, reason=reason,
        extra_data={"from": current_status.value, "to": target_status.value, "version": txn.version},
    )

    logger.info(
        "transaction_state_transition",
        transaction_id=str(transaction_id),
        from_state=current_status.value,
        to_state=target_status.value,
        version=txn.version,
    )
    return txn


async def create_transaction(
    *,
    intent_id: uuid.UUID,
    capability_id: uuid.UUID | None,
    amount_minor: int,
    currency: str,
    idempotency_key: str,
    session: AsyncSession,
) -> Transaction:
    """
    Create the transaction record. Status starts at CREATED.
    Returns existing transaction if idempotency_key already exists.
    """
    # Idempotency check
    result = await session.execute(
        select(Transaction).where(Transaction.idempotency_key == idempotency_key)
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.info("transaction_idempotent_hit", idempotency_key=idempotency_key)
        return existing

    from razorguard.shared.security import generate_id

    txn = Transaction(
        id=uuid.UUID(generate_id()),
        intent_id=intent_id,
        capability_id=capability_id,
        idempotency_key=idempotency_key,
        status=TransactionStatus.CREATED,
        amount_minor=amount_minor,
        currency=currency,
        version=1,
    )
    session.add(txn)
    await session.flush()

    logger.info(
        "transaction_created",
        transaction_id=str(txn.id),
        intent_id=str(intent_id),
        amount=amount_minor,
    )
    return txn
