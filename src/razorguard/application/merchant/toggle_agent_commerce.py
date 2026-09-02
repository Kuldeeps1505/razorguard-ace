"""
ToggleAgentCommerce — merchant kill switch.

One call enables or disables ALL agent commerce for a merchant.
When disabled:
  - New intent creation fails immediately
  - Capability issuance fails immediately
  - In-flight authorized transactions are NOT cancelled
    (they were already authorized before the toggle)

This is one of the most important safety controls in the system.
"""

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.merchant.configure_policy import configure_merchant_policy
from razorguard.application.merchant.schemas import MerchantPolicyRequest, MerchantPolicyResponse
from razorguard.infrastructure.database.repositories.merchant_repository import MerchantRepository
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.errors import MerchantUnavailableError

logger = get_logger(__name__)


async def disable_agent_commerce(
    *,
    merchant_id: uuid.UUID,
    session: AsyncSession,
) -> MerchantPolicyResponse:
    """
    Immediately disable all agent commerce for this merchant.
    Creates a new policy version with agent_commerce_enabled=False.
    """
    merchant_repo = MerchantRepository(session)
    current = await merchant_repo.get_current_policy(merchant_id)
    if not current:
        raise MerchantUnavailableError(str(merchant_id))

    # Preserve all existing settings, just flip the switch
    request = MerchantPolicyRequest(
        agent_commerce_enabled=False,
        max_autonomous_order_minor=current.max_autonomous_order_minor,
        max_discount_pct=current.max_discount_pct,
        max_agent_txns_per_day=current.max_agent_txns_per_day,
        allowed_agent_categories=json.loads(current.allowed_agent_categories),
        allowed_payment_methods=json.loads(current.allowed_payment_methods),
        refund_requires_human=current.refund_requires_human,
    )
    logger.warning("merchant_agent_commerce_disabled", merchant_id=str(merchant_id))
    return await configure_merchant_policy(
        merchant_id=merchant_id,
        request=request,
        session=session,
    )


async def enable_agent_commerce(
    *,
    merchant_id: uuid.UUID,
    session: AsyncSession,
) -> MerchantPolicyResponse:
    """Re-enable agent commerce for a merchant."""
    merchant_repo = MerchantRepository(session)
    current = await merchant_repo.get_current_policy(merchant_id)
    if not current:
        raise MerchantUnavailableError(str(merchant_id))

    request = MerchantPolicyRequest(
        agent_commerce_enabled=True,
        max_autonomous_order_minor=current.max_autonomous_order_minor,
        max_discount_pct=current.max_discount_pct,
        max_agent_txns_per_day=current.max_agent_txns_per_day,
        allowed_agent_categories=json.loads(current.allowed_agent_categories),
        allowed_payment_methods=json.loads(current.allowed_payment_methods),
        refund_requires_human=current.refund_requires_human,
    )
    logger.info("merchant_agent_commerce_enabled", merchant_id=str(merchant_id))
    return await configure_merchant_policy(
        merchant_id=merchant_id,
        request=request,
        session=session,
    )
