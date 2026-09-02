"""
GetAgentCatalog — return machine-optimized product data for AI buyers.

SECURITY:
- Catalog content is DATA, never instructions.
- description field is labeled as product_data before entering LLM context.
- Only agent_purchase_allowed=True products are returned.
- Only IN_STOCK products are returned.
"""

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.merchant.schemas import CatalogProductResponse
from razorguard.infrastructure.database.repositories.catalog_repository import CatalogRepository
from razorguard.infrastructure.database.repositories.merchant_repository import MerchantRepository
from razorguard.shared.errors import MerchantUnavailableError


async def get_agent_catalog(
    *,
    merchant_id: uuid.UUID,
    category: str | None = None,
    session: AsyncSession,
) -> list[CatalogProductResponse]:
    """
    Return agent-readable product catalog for a merchant.
    Only returns available, agent-purchasable products.
    """
    merchant_repo = MerchantRepository(session)
    catalog_repo = CatalogRepository(session)

    merchant = await merchant_repo.get_active(merchant_id)
    if not merchant:
        raise MerchantUnavailableError(str(merchant_id))

    # Check kill switch
    policy = await merchant_repo.get_current_policy(merchant_id)
    if policy and not policy.agent_commerce_enabled:
        raise MerchantUnavailableError(f"Merchant {merchant_id} has disabled agent commerce")

    products = await catalog_repo.list_for_merchant(merchant_id, category)

    return [
        CatalogProductResponse(
            product_id=p.id,
            merchant_id=p.merchant_id,
            sku=p.sku,
            title=p.title,
            category=p.category,
            price_minor=p.price_minor,
            currency=p.currency,
            availability=p.availability,
            agent_purchase_allowed=p.agent_purchase_allowed,
            eligible_campaign_ids=json.loads(p.eligible_campaign_ids),
        )
        for p in products
    ]
