"""
CapabilityRepository — data access for Capability.

Replay protection is enforced here:
a capability that has been used cannot be used again.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.capability import Capability
from razorguard.infrastructure.database.repositories.base_repository import BaseRepository
from razorguard.shared.enums import CapabilityStatus


class CapabilityRepository(BaseRepository[Capability]):
    model = Capability

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active_for_intent(self, intent_id: uuid.UUID) -> Capability | None:
        from razorguard.shared.clock import utcnow

        now = utcnow()
        result = await self._session.execute(
            select(Capability).where(
                Capability.intent_id == intent_id,
                Capability.status == CapabilityStatus.ACTIVE,
                Capability.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_nonce(self, nonce: str) -> Capability | None:
        """Used for replay detection — nonce must be globally unique."""
        result = await self._session.execute(select(Capability).where(Capability.nonce == nonce))
        return result.scalar_one_or_none()
