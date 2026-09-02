"""
ExecutePayment use case — the most critical path in RazorGuard.

Pre-conditions enforced before this is called:
  1. Intent validated (hash, expiry, availability, price)
  2. Policy APPROVED
  3. Consent GRANTED (if required)
  4. Capability issued and not yet consumed
  5. Distributed lock acquired

Execution flow:
  AUTHORIZED → EXECUTING → [SUCCESS | UNKNOWN]

CRITICAL RULES:
  - Never blindly retry UNKNOWN payments
  - Network timeout → UNKNOWN → reconciliation (never FAILED)
  - Amount must exactly match capability.amount_minor
  - Idempotency key prevents duplicate charges on retry
  - Lock must be held for entire execution

BORING BY DESIGN:
  The payment executor does not reason.
  It receives a validated execution command and calls Razorpay.
  That's it.
"""

import uuid

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.authorization.consume_capability import consume_capability
from razorguard.application.policy.evaluate_policy import evaluate_intent_policy
from razorguard.application.transactions.transition_state import (
    create_transaction,
    transition_transaction,
)
from razorguard.infrastructure.cache.locks import acquire_payment_lock
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.observability.metrics import (
    payments_attempted,
    payments_unknown,
)
from razorguard.infrastructure.payments.razorpay_client import create_order
from razorguard.shared.enums import TransactionStatus
from razorguard.shared.errors import (
    CapabilityExpiredError,
)
from razorguard.shared.security import generate_idempotency_key

logger = get_logger(__name__)

PAYMENT_TIMEOUT_SECONDS = 15


async def execute_payment(
    *,
    intent_id: uuid.UUID,
    capability_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    authenticated_agent_id: uuid.UUID,
    request_id: str,
    session_id: str | None = None,
    session: AsyncSession,
    redis: aioredis.Redis,  # type: ignore[type-arg]
) -> dict:
    """
    Execute a payment for a validated, authorized intent.

    Returns a dict with transaction_id, status, and razorpay_order_id.
    Never raises on UNKNOWN — returns UNKNOWN status for reconciliation.
    """
    from razorguard.infrastructure.database.repositories.capability_repository import (
        CapabilityRepository,
    )
    from razorguard.infrastructure.database.repositories.intent_repository import IntentRepository

    intent_repo = IntentRepository(session)
    cap_repo = CapabilityRepository(session)

    # Fetch intent and capability
    intent = await intent_repo.get_by_id_for_user(intent_id, authenticated_user_id)
    if not intent:
        raise CapabilityExpiredError(str(capability_id))

    cap = await cap_repo.get_by_id(capability_id)
    if not cap:
        raise CapabilityExpiredError(str(capability_id))

    await _revalidate_for_execution(intent=intent, cap=cap, authenticated_user_id=authenticated_user_id, session=session)

    # Generate idempotency key — deterministic, prevents duplicate charges
    idempotency_key = generate_idempotency_key(
        str(intent_id),
        str(capability_id),
        str(authenticated_user_id),
        str(cap.amount_minor),
        cap.nonce,
    )

    # Acquire distributed lock — only one execution per intent at a time
    async with acquire_payment_lock(redis, str(intent_id)):
        # Create or fetch existing transaction (idempotency)
        txn = await create_transaction(
            intent_id=intent_id,
            capability_id=capability_id,
            amount_minor=cap.amount_minor,
            currency=cap.currency,
            idempotency_key=idempotency_key,
            session=session,
        )

        # If already terminal, return existing result
        current_status = TransactionStatus(txn.status)
        if current_status.is_terminal:
            logger.info(
                "payment_already_terminal",
                transaction_id=str(txn.id),
                status=current_status.value,
            )
            return {
                "transaction_id": str(txn.id),
                "status": current_status.value,
                "razorpay_order_id": txn.razorpay_order_id,
            }

        # Consume capability — marks as USED (replay protection)
        await consume_capability(
            capability_id=capability_id,
            authenticated_user_id=authenticated_user_id,
            authenticated_agent_id=authenticated_agent_id,
            intent_id=intent_id,
            request_id=request_id,
            session_id=session_id,
            session=session,
        )

        # Transition: CREATED → EXECUTING
        txn = await transition_transaction(
            transaction_id=txn.id,
            target_status=TransactionStatus.EXECUTING,
            expected_version=txn.version,
            session=session,
        )

        payments_attempted.labels(
            payment_method=intent.payment_method,
            merchant_id=str(intent.merchant_id),
        ).inc()

        # Execute payment — may timeout
        razorpay_order_id: str | None = None
        try:
            order = create_order(
                amount_minor=cap.amount_minor,
                currency=cap.currency,
                receipt=idempotency_key,
                notes={
                    "intent_id": str(intent_id),
                    "transaction_id": str(txn.id),
                    "request_id": request_id,
                },
            )
            razorpay_order_id = order.get("id")
            txn.razorpay_order_id = razorpay_order_id
            await session.flush()

            # Order creation is not payment capture. Only verified provider
            # evidence may transition a submitted payment to COMPLETED.
            txn = await transition_transaction(
                transaction_id=txn.id,
                target_status=TransactionStatus.SUBMITTED,
                expected_version=txn.version,
                session=session,
            )
            logger.info(
                "payment_order_created",
                transaction_id=str(txn.id),
                razorpay_order_id=razorpay_order_id,
            )
            return {
                "transaction_id": str(txn.id),
                "status": TransactionStatus.SUBMITTED.value,
                "razorpay_order_id": razorpay_order_id,
            }

        except Exception as exc:
            # Network timeout, connection error, partial response → UNKNOWN
            # NEVER treat as FAILED — query Razorpay to reconcile
            logger.warning(
                "payment_execution_uncertain",
                transaction_id=str(txn.id),
                razorpay_order_id=razorpay_order_id,
                error=str(exc),
            )
            payments_unknown.inc()

            txn = await transition_transaction(
                transaction_id=txn.id,
                target_status=TransactionStatus.UNKNOWN,
                expected_version=txn.version,
                session=session,
                reason=str(exc),
            )

            # Queue for reconciliation (Phase 10)
            _enqueue_reconciliation(str(txn.id))

            # Return UNKNOWN — caller must NOT retry
            return {
                "transaction_id": str(txn.id),
                "status": TransactionStatus.UNKNOWN.value,
                "razorpay_order_id": razorpay_order_id,
            }


def _enqueue_reconciliation(transaction_id: str) -> None:
    """Queue a reconciliation job. Worker implemented in Phase 10."""
    try:
        from apps.worker.tasks import reconcile_unknown_payment

        reconcile_unknown_payment.delay(transaction_id)
        logger.info("reconciliation_queued", transaction_id=transaction_id)
    except Exception as e:
        # If queue is unavailable, log but don't lose the payment state
        logger.error(
            "reconciliation_queue_failed",
            transaction_id=transaction_id,
            error=str(e),
        )


async def _revalidate_for_execution(*, intent, cap, authenticated_user_id: uuid.UUID, session: AsyncSession) -> None:
    """Fail closed if authoritative checkout data or policy changed after consent."""
    from razorguard.domain.intents.hashing import verify_intent_hash
    from razorguard.infrastructure.database.repositories.catalog_repository import CatalogRepository
    from razorguard.infrastructure.database.repositories.merchant_repository import (
        MerchantRepository,
    )
    from razorguard.shared.errors import (
        CapabilityInvalidError,
        MerchantUnavailableError,
        ProductUnavailableError,
    )

    if not verify_intent_hash(
        stored_hash=intent.intent_hash, user_id=intent.user_id, agent_id=intent.agent_id,
        merchant_id=intent.merchant_id, product_id=intent.product_id,
        amount_minor=intent.final_amount_minor, currency=intent.currency,
        category=intent.category, session_id=intent.session_id, expires_at=intent.expires_at,
        payment_method=intent.payment_method, quantity=intent.quantity,
    ):
        raise CapabilityInvalidError("Intent integrity check failed")
    if (cap.intent_hash != intent.intent_hash or cap.merchant_id != intent.merchant_id
            or cap.product_id != intent.product_id or cap.amount_minor != intent.final_amount_minor
            or cap.currency != intent.currency):
        raise CapabilityInvalidError("Capability no longer matches the authorized intent")

    merchant_repo = MerchantRepository(session)
    merchant = await merchant_repo.get_active(intent.merchant_id)
    policy = await merchant_repo.get_current_policy(intent.merchant_id)
    if not merchant or not policy or not policy.agent_commerce_enabled:
        raise MerchantUnavailableError(str(intent.merchant_id))
    if cap.merchant_policy_id != policy.id:
        raise CapabilityInvalidError("Merchant policy changed after authorization")

    product = await CatalogRepository(session).get_available_for_agent(intent.product_id, intent.merchant_id)
    if not product:
        raise ProductUnavailableError(str(intent.product_id))
    if product.price_minor * intent.quantity != intent.amount_minor:
        raise CapabilityInvalidError("Catalog price changed after authorization")

    decision = await evaluate_intent_policy(
        intent_id=intent.id, authenticated_user_id=authenticated_user_id, session=session
    )
    if decision.decision == "DENY":
        raise CapabilityInvalidError(f"Final policy evaluation denied execution: {decision.reason}")
