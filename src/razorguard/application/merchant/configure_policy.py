"""
ConfigureMerchantPolicy — update merchant commerce policy.

Creates a new policy version (old version is preserved for audit).
Kill switch (agent_commerce_enabled=False) takes effect immediately.
"""

import json
import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.merchant.schemas import MerchantPolicyRequest, MerchantPolicyResponse
from razorguard.infrastructure.database.models.merchant import MerchantPolicy
from razorguard.infrastructure.database.repositories.merchant_repository import MerchantRepository
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.errors import MerchantUnavailableError
from razorguard.shared.security import generate_id

logger = get_logger(__name__)


async def configure_merchant_policy(
    *,
    merchant_id: uuid.UUID,
    request: MerchantPolicyRequest,
    session: AsyncSession,
) -> MerchantPolicyResponse:
    """Create a new policy version, deprecating the previous current version."""
    merchant_repo = MerchantRepository(session)

    merchant = await merchant_repo.get_active(merchant_id)
    if not merchant:
        raise MerchantUnavailableError(str(merchant_id))

    # Get current version number
    current_policy = await merchant_repo.get_current_policy(merchant_id)
    next_version = (current_policy.version + 1) if current_policy else 1

    # Deactivate existing current policy
    if current_policy:
        await session.execute(
            update(MerchantPolicy)
            .where(
                MerchantPolicy.merchant_id == merchant_id,
                MerchantPolicy.is_current.is_(True),
            )
            .values(is_current=False)
        )

    # Create new version
    new_policy = MerchantPolicy(
        id=uuid.UUID(generate_id()),
        merchant_id=merchant_id,
        version=next_version,
        agent_commerce_enabled=request.agent_commerce_enabled,
        max_autonomous_order_minor=request.max_autonomous_order_minor,
        max_discount_pct=request.max_discount_pct,
        max_agent_txns_per_day=request.max_agent_txns_per_day,
        allowed_agent_categories=json.dumps(request.allowed_agent_categories),
        allowed_payment_methods=json.dumps(request.allowed_payment_methods),
        refund_requires_human=request.refund_requires_human,
        is_current=True,
    )
    session.add(new_policy)
    await session.flush()

    action = "kill_switch_activated" if not request.agent_commerce_enabled else "policy_updated"
    logger.info(
        action,
        merchant_id=str(merchant_id),
        version=next_version,
        agent_commerce_enabled=request.agent_commerce_enabled,
    )

    return MerchantPolicyResponse(
        policy_id=new_policy.id,
        merchant_id=merchant_id,
        version=next_version,
        agent_commerce_enabled=new_policy.agent_commerce_enabled,
        max_autonomous_order_minor=new_policy.max_autonomous_order_minor,
        max_discount_pct=new_policy.max_discount_pct,
        max_agent_txns_per_day=new_policy.max_agent_txns_per_day,
        allowed_agent_categories=json.loads(new_policy.allowed_agent_categories),
        allowed_payment_methods=json.loads(new_policy.allowed_payment_methods),
        refund_requires_human=new_policy.refund_requires_human,
        is_current=True,
    )
