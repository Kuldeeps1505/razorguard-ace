"""
ExpireIntent — background job to expire stale intents.

Intents that pass their expires_at without completing must
be moved to EXPIRED state. This is handled by the scheduler.
"""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.intent import Intent
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.clock import utcnow
from razorguard.shared.enums import TransactionStatus

logger = get_logger(__name__)

# States that can be expired (non-terminal, non-UNKNOWN)
_EXPIRABLE_STATES = [
    TransactionStatus.CREATED.value,
    TransactionStatus.VALIDATING.value,
    TransactionStatus.POLICY_PENDING.value,
    TransactionStatus.POLICY_APPROVED.value,
    TransactionStatus.AWAITING_CONSENT.value,
    TransactionStatus.CONSENT_GRANTED.value,
]


async def expire_stale_intents(session: AsyncSession) -> int:
    """
    Move all expired, non-terminal intents to EXPIRED status.
    Returns count of intents expired.
    """
    now = utcnow()
    result = await session.execute(
        update(Intent)
        .where(
            Intent.expires_at < now,
            Intent.status.in_(_EXPIRABLE_STATES),
        )
        .values(status=TransactionStatus.EXPIRED.value)
        .returning(Intent.id)
    )
    expired = result.fetchall()
    count = len(expired)
    if count > 0:
        logger.info("intents_expired", count=count)
    return count
