"""
Upsell/cross-sell — returns complementary products from the merchant-configured pool.

SECURITY: Agent can only suggest products from the merchant's configured upsell pool.
It cannot invent its own upsell products or prices.
"""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.catalog_product import CatalogProduct
from razorguard.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def get_complementary_products(
    *,
    purchased_product_id: uuid.UUID,
    merchant_id: uuid.UUID,
    session: AsyncSession,
) -> list[dict]:
    """
    Return upsell/cross-sell products from the purchased product's configured pool.
    Returns empty list if no upsell pool is configured.
    """
    result = await session.execute(
        select(CatalogProduct).where(CatalogProduct.id == purchased_product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        return []

    upsell_ids_raw = json.loads(product.upsell_product_ids or "[]")
    if not upsell_ids_raw:
        return []

    upsells = []
    for uid_str in upsell_ids_raw[:3]:  # max 3 upsell suggestions
        try:
            uid = uuid.UUID(uid_str)
        except ValueError:
            continue
        res = await session.execute(
            select(CatalogProduct).where(
                CatalogProduct.id == uid,
                CatalogProduct.merchant_id == merchant_id,
            )
        )
        upsell_product = res.scalar_one_or_none()
        if upsell_product:
            upsells.append({
                "product_id": str(upsell_product.id),
                "title": upsell_product.title,
                "category": upsell_product.category,
                "price_minor": upsell_product.price_minor,
                "currency": upsell_product.currency,
            })

    return upsells
