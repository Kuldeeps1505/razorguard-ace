"""
CatalogRepository — data access for CatalogProduct.

SECURITY: canonical catalog values are the authoritative source.
LLM-suggested prices/merchants are NEVER trusted directly.
Re-validation queries this repository before payment execution.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.catalog_product import CatalogProduct
from razorguard.infrastructure.database.repositories.base_repository import BaseRepository
from razorguard.shared.enums import ProductAvailability


class CatalogRepository(BaseRepository[CatalogProduct]):
    model = CatalogProduct

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_available_for_agent(
        self, product_id: uuid.UUID, merchant_id: uuid.UUID
    ) -> CatalogProduct | None:
        """
        Fetch a product that is available AND agent-purchasable.
        Used for canonical validation before intent creation and
        final re-validation before payment execution.
        """
        result = await self._session.execute(
            select(CatalogProduct).where(
                CatalogProduct.id == product_id,
                CatalogProduct.merchant_id == merchant_id,
                CatalogProduct.availability == ProductAvailability.IN_STOCK,
                CatalogProduct.agent_purchase_allowed.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_merchant(
        self,
        merchant_id: uuid.UUID,
        category: str | None = None,
    ) -> list[CatalogProduct]:
        """Agent-readable catalog — returns purchasable products."""
        query = select(CatalogProduct).where(
            CatalogProduct.merchant_id == merchant_id,
            CatalogProduct.availability == ProductAvailability.IN_STOCK,
            CatalogProduct.agent_purchase_allowed.is_(True),
        )
        if category:
            query = query.where(CatalogProduct.category == category)

        result = await self._session.execute(query)
        return list(result.scalars().all())
