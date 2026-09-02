"""
RequestConsent use case — create a pending consent for an intent.

Called when policy returns ASK_USER.
Consent is bound to: intent_id + user_id + expires_at.
User must explicitly approve or reject. No implicit approval.

SECURITY:
- Consent token is cryptographically random (replay protection)
- Consent is bound to intent_id — approving one intent cannot
  authorize a different intent
- Duplicate consent for same intent returns existing pending consent
  (idempotent on intent_id + user_id)
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.commerce.quotes import create_quote_for_intent
from razorguard.application.consent.schemas import ConsentResponse
from razorguard.infrastructure.database.models.consent import Consent
from razorguard.infrastructure.database.repositories.intent_repository import IntentRepository
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.observability.metrics import consent_requested
from razorguard.shared.clock import is_expired, utcnow_plus
from razorguard.shared.enums import ConsentMode, ConsentStatus
from razorguard.shared.errors import IntentExpiredError
from razorguard.shared.security import generate_id, generate_nonce

logger = get_logger(__name__)

CONSENT_TTL_SECONDS = 300  # 5 minutes — same as capability TTL


async def request_consent(
    *,
    intent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    session: AsyncSession,
) -> ConsentResponse:
    """
    Create a pending consent request for the authenticated user.
    Returns existing pending consent if one already exists (idempotent).
    """
    intent_repo = IntentRepository(session)

    # Verify intent belongs to user and is not expired
    intent = await intent_repo.get_by_id_for_user(intent_id, authenticated_user_id)
    if not intent:
        raise IntentExpiredError(str(intent_id))
    if is_expired(intent.expires_at):
        raise IntentExpiredError(str(intent_id))
    await create_quote_for_intent(intent=intent, session=session)

    # Check for existing pending consent (idempotency)
    from sqlalchemy import select

    from razorguard.infrastructure.database.models.consent import Consent as ConsentModel

    result = await session.execute(
        select(ConsentModel).where(
            ConsentModel.intent_id == intent_id,
            ConsentModel.user_id == authenticated_user_id,
            ConsentModel.status == ConsentStatus.PENDING,
        )
    )
    existing = result.scalar_one_or_none()
    if existing and not is_expired(existing.expires_at):
        logger.info("consent_already_pending", intent_id=str(intent_id))
        return _to_response(existing)

    expires_at = utcnow_plus(seconds=CONSENT_TTL_SECONDS)
    consent_token = generate_nonce(32)

    consent = ConsentModel(
        id=uuid.UUID(generate_id()),
        intent_id=intent_id,
        user_id=authenticated_user_id,
        mode=ConsentMode.SINGLE_TRANSACTION,
        status=ConsentStatus.PENDING,
        consent_token=consent_token,
        expires_at=expires_at,
    )
    session.add(consent)
    await session.flush()

    consent_requested.inc()
    logger.info(
        "consent_requested",
        consent_id=str(consent.id),
        intent_id=str(intent_id),
        user_id=str(authenticated_user_id),
    )
    return _to_response(consent)


def _to_response(consent: Consent) -> ConsentResponse:
    return ConsentResponse(
        consent_id=consent.id,
        intent_id=consent.intent_id,
        user_id=consent.user_id,
        mode=consent.mode,
        status=consent.status,
        expires_at=consent.expires_at,
        approved_at=consent.approved_at,
        rejected_at=consent.rejected_at,
        reject_reason=consent.reject_reason,
        consent_token=(consent.consent_token if consent.status == ConsentStatus.PENDING else None),
    )
