"""
TransactionRepository — data access for Transaction and PaymentAttempt.

UNKNOWN state transactions are never retried — they go to reconciliation.
All queries scoped by authenticated user/agent.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.payment import PaymentAttempt
from razorguard.infrastructure.database.models.transaction import Transaction
from razorguard.infrastructure.database.repositories.base_repository import BaseRepository
from razorguard.shared.enums import TransactionStatus


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_idempotency_key(self, key: str) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def get_by_razorpay_order(self, order_id: str) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.razorpay_order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def list_unknown(self) -> list[Transaction]:
        """Return all UNKNOWN transactions awaiting reconciliation."""
        result = await self._session.execute(
            select(Transaction).where(Transaction.status == TransactionStatus.UNKNOWN)
        )
        return list(result.scalars().all())

    async def get_by_intent(self, intent_id: uuid.UUID) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.intent_id == intent_id)
        )
        return result.scalar_one_or_none()


class PaymentAttemptRepository(BaseRepository[PaymentAttempt]):
    model = PaymentAttempt

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def count_for_transaction(self, transaction_id: uuid.UUID) -> int:
        from sqlalchemy import func, select

        result = await self._session.execute(
            select(func.count()).where(PaymentAttempt.transaction_id == transaction_id)
        )
        return result.scalar_one()

    async def get_by_provider_idempotency_key(self, key: str) -> PaymentAttempt | None:
        result = await self._session.execute(
            select(PaymentAttempt).where(PaymentAttempt.provider_idempotency_key == key)
        )
        return result.scalar_one_or_none()
