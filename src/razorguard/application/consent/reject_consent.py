"""RejectConsent — user explicitly rejects a pending consent."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.consent.schemas import ConsentResponse
from razorguard.domain.consent.exceptions import ConsentNotPendingError
from razorguard.infrastructure.database.models.consent import Consent
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.observability.metrics import consent_rejected
from razorguard.shared.clock import utcnow
from razorguard.shared.enums import ConsentStatus
from razorguard.shared.errors import RazorGuardError

logger = get_logger(__name__)


async def reject_consent(
    *,
    consent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    reason: str | None,
    session: AsyncSession,
) -> ConsentResponse:
    result = await session.execute(
        select(Consent).where(
            Consent.id == consent_id,
            Consent.user_id == authenticated_user_id,
        )
    )
    consent = result.scalar_one_or_none()
    if not consent:
        raise RazorGuardError(message=f"Consent {consent_id} not found", code="CONSENT_NOT_FOUND")

    if consent.status != ConsentStatus.PENDING:
        raise ConsentNotPendingError(str(consent_id), consent.status)

    consent.status = ConsentStatus.REJECTED
    consent.rejected_at = utcnow()
    consent.reject_reason = reason
    await session.flush()

    consent_rejected.inc()
    logger.info("consent_rejected", consent_id=str(consent_id), user_id=str(authenticated_user_id))

    from razorguard.application.consent.request_consent import _to_response

    return _to_response(consent)
