"""Campaign reservation lifecycle tied to payment finality."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.commerce_controls import CampaignReservation
from razorguard.shared.clock import utcnow, utcnow_plus
from razorguard.shared.security import generate_id


async def reserve_campaign(
    *, campaign_id: uuid.UUID, intent_id: uuid.UUID, agent_id: uuid.UUID, session: AsyncSession
) -> CampaignReservation:
    existing = await session.scalar(select(CampaignReservation).where(CampaignReservation.intent_id == intent_id))
    if existing:
        return existing
        reservation = CampaignReservation(
            id=uuid.UUID(generate_id()), campaign_id=campaign_id,
            intent_id=intent_id, agent_id=agent_id, status="RESERVED",
            expires_at=utcnow_plus(minutes=10),
        )
    session.add(reservation)
    await session.flush()
    return reservation


async def settle_campaign_for_intent(*, intent_id: uuid.UUID, captured: bool, session: AsyncSession) -> None:
    values = {"status": "CONSUMED" if captured else "RELEASED"}
    if captured:
        values["consumed_at"] = utcnow()
    reservation = await session.scalar(select(CampaignReservation).where(
        CampaignReservation.intent_id == intent_id, CampaignReservation.status == "RESERVED"
    ))
    if not reservation:
        return
    await session.execute(update(CampaignReservation).where(
        CampaignReservation.intent_id == intent_id, CampaignReservation.status == "RESERVED"
    ).values(**values))
    if not captured:
        from razorguard.infrastructure.database.models.campaign import Campaign
        await session.execute(update(Campaign).where(Campaign.id == reservation.campaign_id, Campaign.total_uses > 0).values(total_uses=Campaign.total_uses - 1))


async def release_expired_campaign_reservations(*, session: AsyncSession) -> int:
    """Release abandoned offer holds; intended for a scheduled worker run."""
    expired = list((await session.scalars(select(CampaignReservation).where(
        CampaignReservation.status == "RESERVED", CampaignReservation.expires_at <= utcnow()
    ))).all())
    for reservation in expired:
        await settle_campaign_for_intent(intent_id=reservation.intent_id, captured=False, session=session)
    return len(expired)
