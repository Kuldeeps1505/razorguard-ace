"""
ApproveConsent — user explicitly approves a pending consent.

SECURITY:
- Consent must be PENDING (not already used/expired/rejected)
- Consent must not be expired
- consent_token must match (prevents forged approvals)
- Consent is bound to intent_id — approving one cannot authorize another
- One-time use: APPROVED → marks used_at immediately
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.audit.record_event import record_audit_event
from razorguard.application.consent.schemas import ConsentResponse
from razorguard.domain.consent.exceptions import (
    ConsentAlreadyUsedError,
    ConsentIntentMismatchError,
    ConsentNotPendingError,
)
from razorguard.infrastructure.database.models.consent import Consent
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.observability.metrics import consent_granted
from razorguard.shared.clock import is_expired, utcnow
from razorguard.shared.enums import AuditActor, ConsentStatus
from razorguard.shared.errors import ConsentExpiredError, RazorGuardError

logger = get_logger(__name__)


async def approve_consent(
    *,
    consent_id: uuid.UUID,
    intent_id: uuid.UUID,
    consent_token: str,
    authenticated_user_id: uuid.UUID,
    session: AsyncSession,
) -> ConsentResponse:
    """
    Approve a pending consent.
    Raises on any security check failure.
    """
    result = await session.execute(
        select(Consent).where(
            Consent.id == consent_id,
            Consent.user_id == authenticated_user_id,  # tenant isolation
        )
    )
    consent = result.scalar_one_or_none()
    if not consent:
        raise RazorGuardError(
            message=f"Consent {consent_id} not found",
            code="CONSENT_NOT_FOUND",
        )

    # Binding check — consent must be for the specified intent
    if consent.intent_id != intent_id:
        raise ConsentIntentMismatchError(str(consent_id), str(intent_id))

    # Status check
    if consent.status == ConsentStatus.USED:
        raise ConsentAlreadyUsedError(str(consent_id))
    if consent.status == ConsentStatus.REJECTED:
        raise ConsentNotPendingError(str(consent_id), consent.status)
    if consent.status != ConsentStatus.PENDING:
        raise ConsentNotPendingError(str(consent_id), consent.status)

    # Expiry check
    if is_expired(consent.expires_at):
        consent.status = ConsentStatus.EXPIRED
        await session.flush()
        raise ConsentExpiredError(str(consent_id))

    # Token verification — prevent forged approvals
    if consent.consent_token != consent_token:
        logger.warning(
            "consent_token_mismatch",
            consent_id=str(consent_id),
            user_id=str(authenticated_user_id),
        )
        raise RazorGuardError(
            message="Consent token mismatch",
            code="CONSENT_TOKEN_INVALID",
        )

    # Approve
    now = utcnow()
    consent.status = ConsentStatus.APPROVED
    consent.approved_at = now
    await session.flush()
    await record_audit_event(
        session=session, request_id=f"consent:{consent.id}", actor=AuditActor.USER,
        action="consent.approved", result="SUCCESS", intent_id=consent.intent_id,
        actor_id=str(authenticated_user_id), reason="User approved the canonical checkout quote",
        extra_data={"consent_id": str(consent.id)},
    )

    consent_granted.inc()
    logger.info(
        "consent_granted",
        consent_id=str(consent_id),
        intent_id=str(intent_id),
        user_id=str(authenticated_user_id),
    )

    from razorguard.application.consent.request_consent import _to_response

    return _to_response(consent)
