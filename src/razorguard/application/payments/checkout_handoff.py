"""
CheckoutHandoff — orchestrates the full authorization → payment pipeline.

This is the single endpoint that takes an intent from CREATED
all the way to a Razorpay order being created.

Flow:
  intent_id
      ↓
  1. Re-validate intent (price, merchant, hash)
  2. Evaluate dual-sided policy (user + merchant)
  3. Request / auto-approve consent (if below threshold)
  4. Issue execution capability
  5. Execute payment via Razorpay
      ↓
  Returns: transaction_id, razorpay_order_id, status

This is what the frontend "Approve & Pay" button calls.
"""

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.authorization.issue_capability import issue_capability
from razorguard.application.consent.approve_consent import approve_consent
from razorguard.application.consent.request_consent import request_consent
from razorguard.application.intents.validate_intent import validate_intent_for_execution
from razorguard.application.transactions.transition_state import (
    create_transaction,
    transition_transaction,
)
from razorguard.domain.policy.context import (
    IntentEvaluationContext,
    MerchantPolicyContext,
    SpendingContext,
    UserPolicyContext,
)
from razorguard.domain.policy.engine import evaluate_policy
from razorguard.infrastructure.database.repositories.agent_repository import AgentRepository
from razorguard.infrastructure.database.repositories.merchant_repository import MerchantRepository
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.payments.razorpay_client import create_order
from razorguard.shared.clock import utcnow
from razorguard.shared.enums import ConsentStatus, PolicyDecision, TransactionStatus
from razorguard.shared.errors import (
    PolicyDeniedError,
    PolicyUnavailableError,
)
from razorguard.shared.security import generate_id, generate_idempotency_key

logger = get_logger(__name__)


async def checkout_and_pay(
    *,
    intent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    authenticated_agent_id: uuid.UUID,
    request_id: str,
    session_id: str,
    session: AsyncSession,
    redis=None,
) -> dict:
    """
    Orchestrate: intent → policy → consent → capability → Razorpay order.

    Returns dict with transaction_id, razorpay_order_id, status.
    """
    agent_repo = AgentRepository(session)
    merchant_repo = MerchantRepository(session)

    # ── 1. Re-validate intent ─────────────────────────────────
    intent = await validate_intent_for_execution(
        intent_id=intent_id,
        authenticated_user_id=authenticated_user_id,
        session=session,
    )
    logger.info("checkout_intent_validated", intent_id=str(intent_id))

    # ── 2. Evaluate dual-sided policy ─────────────────────────
    merchant_policy_db = await merchant_repo.get_current_policy(intent.merchant_id)
    if not merchant_policy_db:
        raise PolicyUnavailableError()

    merchant_policy = MerchantPolicyContext(
        merchant_policy_id=merchant_policy_db.id,
        policy_version=merchant_policy_db.version,
        agent_commerce_enabled=merchant_policy_db.agent_commerce_enabled,
        max_autonomous_order_minor=merchant_policy_db.max_autonomous_order_minor,
        max_discount_pct=merchant_policy_db.max_discount_pct,
        max_agent_txns_per_day=merchant_policy_db.max_agent_txns_per_day,
        allowed_agent_categories=json.loads(merchant_policy_db.allowed_agent_categories),
        allowed_payment_methods=json.loads(merchant_policy_db.allowed_payment_methods),
        refund_requires_human=merchant_policy_db.refund_requires_human,
    )

    # Load delegation for user policy context
    delegation = await agent_repo.get_active_delegation(
        user_id=authenticated_user_id,
        agent_id=authenticated_agent_id,
    )

    user_policy = UserPolicyContext(
        policy_version_id=uuid.uuid4(),
        policy_version=1,
        max_single_transaction_minor=delegation.max_transaction_minor if delegation else 500_000,
        daily_limit_minor=delegation.max_daily_spend_minor if delegation else 2_000_000,
        monthly_limit_minor=0,
        require_consent_above_minor=delegation.require_consent_above_minor if delegation else 200_000,
        allowed_categories=json.loads(delegation.allowed_categories) if delegation else [],
        allowed_merchant_ids=json.loads(delegation.allowed_merchant_ids) if delegation else [],
        blocked_merchant_ids=json.loads(delegation.blocked_merchant_ids) if delegation else [],
        allowed_payment_methods=json.loads(delegation.allowed_currencies) if delegation else ["INR"],
        allowed_currencies=["INR"],
    )

    ctx = IntentEvaluationContext(
        intent_id=intent.id,
        user_id=intent.user_id,
        agent_id=intent.agent_id,
        merchant_id=intent.merchant_id,
        product_id=intent.product_id,
        amount_minor=intent.amount_minor,
        final_amount_minor=intent.final_amount_minor,
        currency=intent.currency,
        category=intent.category,
        payment_method=intent.payment_method,
        quantity=intent.quantity,
        user_policy=user_policy,
        merchant_policy=merchant_policy,
        spending=SpendingContext(daily_spend_minor=0, monthly_spend_minor=0),
        agent_active=True,
        delegation_active=delegation is not None,
        evaluated_at=utcnow(),
        request_id=request_id,
    )

    policy_result = evaluate_policy(ctx)
    logger.info(
        "checkout_policy_evaluated",
        decision=policy_result.decision.value,
        intent_id=str(intent_id),
    )

    if policy_result.denied:
        raise PolicyDeniedError(
            reason=policy_result.reason,
            blocking_rule=policy_result.blocking_rule or "",
        )

    # ── 3. Consent handling ───────────────────────────────────
    if policy_result.needs_consent:
        consent = await request_consent(
            intent_id=intent_id,
            authenticated_user_id=authenticated_user_id,
            session=session,
        )
        if consent.status == ConsentStatus.PENDING:
            from sqlalchemy import update
            from razorguard.infrastructure.database.models.intent import Intent
            await session.execute(
                update(Intent)
                .where(Intent.id == intent_id)
                .values(status=TransactionStatus.AWAITING_CONSENT.value)
            )
            await session.flush()
            logger.info("checkout_paused_for_consent", intent_id=str(intent_id))
            return {
                "status": "AWAITING_CONSENT",
                "intent_id": str(intent_id),
                "message": "User consent required to proceed.",
            }
        logger.info("checkout_consent_already_granted", intent_id=str(intent_id))

    # ── 4. Transition intent through proper states ────────────
    from sqlalchemy import update
    from razorguard.infrastructure.database.models.intent import Intent
    await session.execute(
        update(Intent)
        .where(Intent.id == intent_id)
        .values(status=TransactionStatus.POLICY_APPROVED.value)
    )
    await session.flush()

    # ── 5. Issue capability ───────────────────────────────────
    capability = await issue_capability(
        intent_id=intent_id,
        authenticated_user_id=authenticated_user_id,
        request_id=request_id,
        session_id=session_id,
        session=session,
    )
    logger.info("checkout_capability_issued", capability_id=str(capability.id))

    # ── 6. Create transaction record and advance through states ─
    idempotency_key = generate_idempotency_key(
        str(intent_id),
        str(capability.id),
        str(authenticated_user_id),
        str(intent.final_amount_minor),
        capability.nonce,
    )

    txn = await create_transaction(
        intent_id=intent_id,
        capability_id=capability.id,
        amount_minor=intent.final_amount_minor,
        currency=intent.currency,
        idempotency_key=idempotency_key,
        session=session,
    )

    # Advance through required intermediate states to reach EXECUTING
    for target in [
        TransactionStatus.VALIDATING,
        TransactionStatus.POLICY_PENDING,
        TransactionStatus.POLICY_APPROVED,
        TransactionStatus.AUTHORIZED,
        TransactionStatus.EXECUTING,
    ]:
        txn = await transition_transaction(
            transaction_id=txn.id,
            target_status=target,
            expected_version=txn.version,
            session=session,
        )

    try:
        order = create_order(
            amount_minor=intent.final_amount_minor,
            currency=intent.currency,
            receipt=idempotency_key[:40],
            notes={
                "intent_id": str(intent_id),
                "transaction_id": str(txn.id),
                "request_id": request_id,
                "razorguard": "true",
            },
        )
        razorpay_order_id = order["id"]

        # Update transaction with Razorpay order ID
        from razorguard.infrastructure.database.models.transaction import Transaction
        from sqlalchemy import update as sa_update
        await session.execute(
            sa_update(Transaction)
            .where(Transaction.id == txn.id)
            .values(razorpay_order_id=razorpay_order_id)
        )

        # Transition to SUBMITTED (Order Created). 
        # Webhook will handle transition to COMPLETED.
        txn = await transition_transaction(
            transaction_id=txn.id,
            target_status=TransactionStatus.SUBMITTED,
            expected_version=txn.version,
            session=session,
        )

        from razorguard.infrastructure.database.models.intent import Intent
        await session.execute(
            sa_update(Intent)
            .where(Intent.id == intent_id)
            .values(status=TransactionStatus.SUBMITTED.value)
        )
        await session.flush()

        logger.info(
            "checkout_payment_created",
            transaction_id=str(txn.id),
            razorpay_order_id=razorpay_order_id,
            amount=intent.final_amount_minor,
        )

        return {
            "status": "success",
            "transaction_id": str(txn.id),
            "intent_id": str(intent_id),
            "razorpay_order_id": razorpay_order_id,
            "amount_minor": intent.final_amount_minor,
            "currency": intent.currency,
            "capability_id": str(capability.id),
            "policy_decision": policy_result.decision.value,
        }

    except Exception as exc:
        # Network timeout → UNKNOWN → reconciliation
        logger.warning("checkout_payment_uncertain", error=str(exc), intent_id=str(intent_id))
        txn = await transition_transaction(
            transaction_id=txn.id,
            target_status=TransactionStatus.UNKNOWN,
            expected_version=txn.version,
            session=session,
        )
        
        from razorguard.infrastructure.database.models.intent import Intent
        from sqlalchemy import update as sa_update
        await session.execute(
            sa_update(Intent)
            .where(Intent.id == intent_id)
            .values(status=TransactionStatus.UNKNOWN.value)
        )
        await session.flush()

        return {
            "status": "unknown",
            "transaction_id": str(txn.id),
            "intent_id": str(intent_id),
            "razorpay_order_id": None,
            "error": str(exc),
            "message": "Payment outcome uncertain. Queued for reconciliation.",
        }
