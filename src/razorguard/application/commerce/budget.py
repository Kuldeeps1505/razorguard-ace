"""Atomic delegated-budget reservations.

Reservations count immediately, preventing concurrent capabilities from
oversubscribing a user's delegated daily allowance.
"""

import uuid

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.commerce_controls import BudgetReservation
from razorguard.shared.clock import utcnow
from razorguard.shared.errors import CapabilityInvalidError
from razorguard.shared.security import generate_id


async def reserve_budget(*, intent, daily_limit_minor: int, expires_at, session: AsyncSession) -> BudgetReservation:
    """Create one reservation per intent under a user-scoped advisory lock."""
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"budget:{intent.user_id}"})
    existing = await session.scalar(select(BudgetReservation).where(BudgetReservation.intent_id == intent.id))
    if existing and existing.status == "RESERVED":
        return existing
    held = await session.scalar(select(func.coalesce(func.sum(BudgetReservation.amount_minor), 0)).where(
        BudgetReservation.user_id == intent.user_id, BudgetReservation.status == "RESERVED",
        BudgetReservation.expires_at > utcnow(),
    )) or 0
    if held + intent.final_amount_minor > daily_limit_minor:
        raise CapabilityInvalidError("Daily delegated budget exhausted by active reservations")
    reservation = BudgetReservation(id=uuid.UUID(generate_id()), user_id=intent.user_id, intent_id=intent.id,
        amount_minor=intent.final_amount_minor, currency=intent.currency, status="RESERVED", expires_at=expires_at)
    session.add(reservation)
    await session.flush()
    return reservation


async def settle_budget_for_intent(*, intent_id: uuid.UUID, status: str, session: AsyncSession) -> None:
    """Captured payments settle; failed/expired/cancelled reservations release."""
    target = "SETTLED" if status == "COMPLETED" else "RELEASED"
    values = {"status": target}
    if target == "RELEASED":
        values["released_at"] = utcnow()
    await session.execute(update(BudgetReservation).where(
        BudgetReservation.intent_id == intent_id, BudgetReservation.status == "RESERVED"
    ).values(**values))
