"""
EvaluatePolicy use case — builds context from DB and runs the policy engine.

This is called:
1. After intent creation (initial policy evaluation)
2. Before capability issuance (re-evaluation)
3. During policy simulation (no side effects)
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.policy.schemas import (
    PolicyDecisionResponse,
    PolicySimulateRequest,
    RuleResultSchema,
)
from razorguard.domain.policy.context import (
    IntentEvaluationContext,
    MerchantPolicyContext,
    SpendingContext,
    UserPolicyContext,
)
from razorguard.domain.policy.simulator import simulate_policy
from razorguard.infrastructure.database.repositories.agent_repository import AgentRepository
from razorguard.infrastructure.database.repositories.intent_repository import IntentRepository
from razorguard.infrastructure.database.repositories.merchant_repository import MerchantRepository
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.clock import utcnow
from razorguard.shared.errors import (
    InvalidIntentError,
    MerchantUnavailableError,
    PolicyUnavailableError,
)

logger = get_logger(__name__)


async def evaluate_intent_policy(
    *,
    intent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    session: AsyncSession,
) -> PolicyDecisionResponse:
    """
    Evaluate policy for an existing intent.
    Builds context from DB, runs engine, returns decision.
    """
    intent_repo = IntentRepository(session)
    agent_repo = AgentRepository(session)
    merchant_repo = MerchantRepository(session)

    # Fetch intent (scoped to user)
    intent = await intent_repo.get_by_id_for_user(intent_id, authenticated_user_id)
    if not intent:
        raise InvalidIntentError(f"Intent {intent_id} not found")

    # Fetch agent + delegation
    agent = await agent_repo.get_active(intent.agent_id)
    agent_active = agent is not None
    delegation = await agent_repo.get_active_delegation(
        user_id=authenticated_user_id,
        agent_id=intent.agent_id,
    )
    delegation_active = delegation is not None

    # Fetch merchant + current policy
    merchant = await merchant_repo.get_active(intent.merchant_id)
    if not merchant:
        raise MerchantUnavailableError(str(intent.merchant_id))
    merchant_policy_db = await merchant_repo.get_current_policy(intent.merchant_id)
    if not merchant_policy_db:
        raise PolicyUnavailableError()

    # Fetch user's current policy version

    # Simplified for now — full user policy loading in Phase 5
    # pv_result unused until Phase 5 wires real user policy lookup
    import json

    user_policy = UserPolicyContext(
        policy_version_id=uuid.uuid4(),
        policy_version=1,
        max_single_transaction_minor=500_000,  # ₹5,000
        daily_limit_minor=2_000_000,  # ₹20,000
        monthly_limit_minor=0,
        require_consent_above_minor=200_000,  # ₹2,000
        allowed_categories=[],
        allowed_merchant_ids=[],
        blocked_merchant_ids=[],
        allowed_payment_methods=["UPI", "CARD"],
        allowed_currencies=["INR"],
    )

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
        agent_active=agent_active,
        delegation_active=delegation_active,
        evaluated_at=utcnow(),
        request_id="",
    )

    result = simulate_policy(ctx)
    return _to_response(result)


async def simulate_policy_for_request(
    *,
    request: PolicySimulateRequest,
    authenticated_user_id: uuid.UUID,
    session: AsyncSession,
) -> PolicyDecisionResponse:
    """
    Simulate policy for a hypothetical transaction.
    No persistence. Pure evaluation.
    """
    import json

    from razorguard.infrastructure.database.repositories.merchant_repository import (
        MerchantRepository,
    )

    merchant_repo = MerchantRepository(session)
    merchant_policy_db = await merchant_repo.get_current_policy(request.merchant_id)

    # Build merchant policy context
    if merchant_policy_db:
        merchant_policy = MerchantPolicyContext(
            merchant_policy_id=merchant_policy_db.id,
            policy_version=merchant_policy_db.version,
            agent_commerce_enabled=merchant_policy_db.agent_commerce_enabled,
            max_autonomous_order_minor=(
                request.override_merchant_max_autonomous_order_minor
                or merchant_policy_db.max_autonomous_order_minor
            ),
            max_discount_pct=merchant_policy_db.max_discount_pct,
            max_agent_txns_per_day=merchant_policy_db.max_agent_txns_per_day,
            allowed_agent_categories=json.loads(merchant_policy_db.allowed_agent_categories),
            allowed_payment_methods=json.loads(merchant_policy_db.allowed_payment_methods),
            refund_requires_human=merchant_policy_db.refund_requires_human,
        )
    else:
        # Default permissive merchant policy for simulation
        merchant_policy = MerchantPolicyContext(
            merchant_policy_id=uuid.uuid4(),
            policy_version=0,
            agent_commerce_enabled=True,
            max_autonomous_order_minor=(
                request.override_merchant_max_autonomous_order_minor or 1_000_000
            ),
            max_discount_pct=10,
            max_agent_txns_per_day=100,
            allowed_agent_categories=[],
            allowed_payment_methods=["UPI", "CARD"],
            refund_requires_human=True,
        )

    user_policy = UserPolicyContext(
        policy_version_id=uuid.uuid4(),
        policy_version=1,
        max_single_transaction_minor=request.override_max_single_transaction_minor or 500_000,
        daily_limit_minor=request.override_daily_limit_minor or 2_000_000,
        monthly_limit_minor=0,
        require_consent_above_minor=request.override_require_consent_above_minor or 200_000,
        allowed_categories=[],
        allowed_merchant_ids=[],
        blocked_merchant_ids=[],
        allowed_payment_methods=["UPI", "CARD"],
        allowed_currencies=["INR"],
    )

    ctx = IntentEvaluationContext(
        intent_id=uuid.uuid4(),
        user_id=authenticated_user_id,
        agent_id=uuid.uuid4(),
        merchant_id=request.merchant_id,
        product_id=request.product_id,
        amount_minor=request.amount_minor,
        final_amount_minor=request.amount_minor,
        currency=request.currency.upper(),
        category=request.category,
        payment_method=request.payment_method.upper(),
        quantity=request.quantity,
        user_policy=user_policy,
        merchant_policy=merchant_policy,
        spending=SpendingContext(
            daily_spend_minor=request.daily_spend_minor,
            monthly_spend_minor=request.monthly_spend_minor,
        ),
        agent_active=True,
        delegation_active=True,
        evaluated_at=utcnow(),
        request_id="simulator",
    )

    result = simulate_policy(ctx)
    return _to_response(result)


def _to_response(result) -> PolicyDecisionResponse:
    return PolicyDecisionResponse(
        decision=result.decision,
        reason=result.reason,
        rule_results=[
            RuleResultSchema(
                rule_name=r.rule_name,
                passed=r.passed,
                reason=r.reason,
                rule_value=r.rule_value,
                actual_value=r.actual_value,
            )
            for r in result.rule_results
        ],
        blocking_rule=result.blocking_rule,
        policy_version_id=result.policy_version_id,
        merchant_policy_id=result.merchant_policy_id,
        evaluated_at=result.evaluated_at,
    )
