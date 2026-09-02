"""MerchantRepository — data access for Merchant and MerchantPolicy."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.campaign import Campaign
from razorguard.infrastructure.database.models.merchant import Merchant, MerchantPolicy
from razorguard.infrastructure.database.repositories.base_repository import BaseRepository
from razorguard.shared.enums import MerchantStatus


class MerchantRepository(BaseRepository[Merchant]):
    model = Merchant

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active(self, merchant_id: uuid.UUID) -> Merchant | None:
        result = await self._session.execute(
            select(Merchant).where(
                Merchant.id == merchant_id,
                Merchant.status == MerchantStatus.ACTIVE,
            )
        )
        return result.scalar_one_or_none()

    async def get_current_policy(self, merchant_id: uuid.UUID) -> MerchantPolicy | None:
        result = await self._session.execute(
            select(MerchantPolicy).where(
                MerchantPolicy.merchant_id == merchant_id,
                MerchantPolicy.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_campaigns(self, merchant_id: uuid.UUID) -> list[Campaign]:
        result = await self._session.execute(
            select(Campaign)
            .where(Campaign.merchant_id == merchant_id)
            .order_by(Campaign.created_at.desc())
        )
        return list(result.scalars().all())
