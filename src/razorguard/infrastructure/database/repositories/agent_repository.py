"""AgentRepository — data access for Agent and Delegation."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.agent import Agent
from razorguard.infrastructure.database.models.delegation import Delegation
from razorguard.infrastructure.database.repositories.base_repository import BaseRepository
from razorguard.shared.enums import AgentStatus, DelegationStatus


class AgentRepository(BaseRepository[Agent]):
    model = Agent

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active(self, agent_id: uuid.UUID) -> Agent | None:
        result = await self._session.execute(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.status == AgentStatus.ACTIVE,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_credential_hash(self, credential_hash: str) -> Agent | None:
        result = await self._session.execute(
            select(Agent).where(Agent.credential_hash == credential_hash)
        )
        return result.scalar_one_or_none()

    async def get_active_delegation(
        self, user_id: uuid.UUID, agent_id: uuid.UUID
    ) -> Delegation | None:
        from razorguard.shared.clock import utcnow

        now = utcnow()
        result = await self._session.execute(
            select(Delegation).where(
                Delegation.user_id == user_id,
                Delegation.agent_id == agent_id,
                Delegation.status == DelegationStatus.ACTIVE,
                Delegation.valid_from <= now,
                Delegation.valid_until >= now,
            )
        )
        return result.scalar_one_or_none()
