"""Canonical signed checkout quotes used for human approval and execution binding."""

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.commerce_controls import CheckoutQuote
from razorguard.shared.clock import utcnow_plus
from razorguard.shared.security import generate_id


async def create_quote_for_intent(*, intent, session: AsyncSession) -> CheckoutQuote:
    existing = await session.scalar(select(CheckoutQuote).where(CheckoutQuote.intent_id == intent.id))
    if existing:
        return existing
    payload = {"intent_id": str(intent.id), "merchant_id": str(intent.merchant_id),
               "product_id": str(intent.product_id), "quantity": intent.quantity,
               "base_amount_minor": intent.amount_minor, "discount_minor": intent.discount_minor,
               "final_amount_minor": intent.final_amount_minor, "currency": intent.currency,
               "intent_hash": intent.intent_hash, "expires_at": intent.expires_at.isoformat()}
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    quote = CheckoutQuote(id=uuid.UUID(generate_id()), intent_id=intent.id,
        quote_hash=hashlib.sha256(serialized.encode()).hexdigest(), canonical_payload=serialized,
        status="ACTIVE", expires_at=utcnow_plus(seconds=300))
    session.add(quote)
    await session.flush()
    return quote
