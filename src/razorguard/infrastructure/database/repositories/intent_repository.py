"""
IntentRepository — data access for Intent entities.

SECURITY: every query is scoped by user_id derived from
the authenticated principal — NEVER from the request body or LLM.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.intent import Intent
from razorguard.infrastructure.database.repositories.base_repository import BaseRepository
from razorguard.shared.enums import TransactionStatus


class IntentRepository(BaseRepository[Intent]):
    model = Intent

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_hash(self, intent_hash: str) -> Intent | None:
        result = await self._session.execute(
            select(Intent).where(Intent.intent_hash == intent_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_user(self, intent_id: uuid.UUID, user_id: uuid.UUID) -> Intent | None:
        """Scoped query — user can only access their own intents."""
        result = await self._session.execute(
            select(Intent).where(
                Intent.id == intent_id,
                Intent.user_id == user_id,  # authorization scope
            )
        )
        return result.scalar_one_or_none()

    async def list_recent_for_user(self, user_id: uuid.UUID, *, limit: int = 50) -> list[Intent]:
        result = await self._session.execute(
            select(Intent)
            .where(Intent.user_id == user_id)
            .order_by(Intent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[Intent]:
        """Return non-terminal intents for a user."""
        terminal = [s.value for s in TransactionStatus if s.is_terminal]
        result = await self._session.execute(
            select(Intent).where(
                Intent.user_id == user_id,
                Intent.status.notin_(terminal),  # type: ignore[attr-defined]
            )
        )
        return list(result.scalars().all())
