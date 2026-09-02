"""Bounded delegated-payment mandates for agentic commerce."""

import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.consent import ConsentMandate
from razorguard.shared.clock import utcnow
from razorguard.shared.enums import ConsentStatus
from razorguard.shared.errors import CapabilityInvalidError
from razorguard.shared.security import generate_id


async def create_mandate(*, user_id: uuid.UUID, agent_id: uuid.UUID, merchant_id: uuid.UUID,
                         max_amount_per_txn_minor: int, max_daily_amount_minor: int,
                         allowed_categories: list[str], valid_until: datetime,
                         session: AsyncSession) -> ConsentMandate:
    if max_amount_per_txn_minor <= 0 or max_daily_amount_minor < max_amount_per_txn_minor:
        raise CapabilityInvalidError("Mandate limits are invalid")
    mandate = ConsentMandate(id=uuid.UUID(generate_id()), user_id=user_id, agent_id=agent_id,
        merchant_id=merchant_id, max_amount_per_txn_minor=max_amount_per_txn_minor,
        max_daily_amount_minor=max_daily_amount_minor,
        allowed_categories=json.dumps([category.lower() for category in allowed_categories]),
        valid_from=utcnow(), valid_until=valid_until, status=ConsentStatus.APPROVED)
    session.add(mandate)
    await session.flush()
    return mandate


async def get_active_mandate_for_intent(*, intent, session: AsyncSession) -> ConsentMandate | None:
    mandate = await session.scalar(select(ConsentMandate).where(
        ConsentMandate.user_id == intent.user_id, ConsentMandate.agent_id == intent.agent_id,
        ConsentMandate.merchant_id == intent.merchant_id, ConsentMandate.status == ConsentStatus.APPROVED,
        ConsentMandate.revoked_at.is_(None), ConsentMandate.valid_from <= utcnow(),
        ConsentMandate.valid_until >= utcnow()))
    if not mandate:
        return None
    categories = json.loads(mandate.allowed_categories)
    eligible = (
        intent.final_amount_minor <= mandate.max_amount_per_txn_minor
        and (not categories or intent.category.lower() in categories)
    )
    return mandate if eligible else None


async def revoke_mandate(*, mandate_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession) -> ConsentMandate:
    mandate = await session.scalar(select(ConsentMandate).where(ConsentMandate.id == mandate_id, ConsentMandate.user_id == user_id))
    if not mandate:
        raise CapabilityInvalidError("Mandate not found")
    mandate.status, mandate.revoked_at = ConsentStatus.REJECTED, utcnow()
    await session.flush()
    return mandate
