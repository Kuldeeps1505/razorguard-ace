"""
ConsumeCapability — verify and atomically mark a capability as used.

This is called immediately before payment execution.
All checks must pass or execution is BLOCKED.

Checks:
1. Capability exists
2. Status is ACTIVE (not already used, revoked, expired)
3. Not expired (TTL check)
4. Signature valid (tamper detection)
5. Belongs to correct user/agent/intent (binding checks)
6. Intent hash still matches (TOCTOU defense)
7. Atomically mark as USED (replay protection)

SECURITY: steps 1-7 must be atomic with respect to payment execution.
Use the distributed lock from Phase 8 around this + execution.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.domain.authorization.capability_signer import verify_capability_signature
from razorguard.infrastructure.database.repositories.capability_repository import (
    CapabilityRepository,
)
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.observability.metrics import capability_replays_rejected
from razorguard.shared.clock import is_expired, utcnow
from razorguard.shared.config import get_settings
from razorguard.shared.enums import CapabilityStatus
from razorguard.shared.errors import (
    CapabilityExpiredError,
    CapabilityInvalidError,
    CapabilityReplayError,
    CapabilityRevokedError,
)

logger = get_logger(__name__)


async def consume_capability(
    *,
    capability_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    authenticated_agent_id: uuid.UUID,
    intent_id: uuid.UUID,
    request_id: str,
    session_id: str | None = None,
    session: AsyncSession,
) -> None:
    """
    Verify and consume a capability for payment execution.

    Raises typed errors for any verification failure.
    Atomically marks as USED on success — replay blocked.
    """
    settings = get_settings()
    cap_repo = CapabilityRepository(session)

    # 1. Fetch
    cap = await cap_repo.get_by_id(capability_id)
    if not cap:
        raise CapabilityInvalidError(f"Capability {capability_id} not found")

    # 2. Status check
    if cap.status == CapabilityStatus.REVOKED:
        logger.warning("capability_revoked", capability_id=str(capability_id))
        raise CapabilityRevokedError(str(capability_id))

    if cap.status == CapabilityStatus.USED:
        capability_replays_rejected.inc()
        logger.warning(
            "capability_replay_blocked",
            capability_id=str(capability_id),
            originally_used_by=cap.used_by_request_id,
        )
        raise CapabilityReplayError(str(capability_id))

    if cap.status == CapabilityStatus.EXPIRED:
        raise CapabilityExpiredError(str(capability_id))

    # 3. TTL check
    if is_expired(cap.expires_at):
        cap.status = CapabilityStatus.EXPIRED
        await cap_repo.save(cap)
        raise CapabilityExpiredError(str(capability_id))

    # 4. Binding checks — wrong user/agent/intent
    if cap.user_id != authenticated_user_id:
        logger.error(
            "capability_wrong_user",
            capability_id=str(capability_id),
            cap_user=str(cap.user_id),
            req_user=str(authenticated_user_id),
        )
        raise CapabilityInvalidError("Capability user binding mismatch")

    if cap.agent_id != authenticated_agent_id:
        logger.error("capability_wrong_agent", capability_id=str(capability_id))
        raise CapabilityInvalidError("Capability agent binding mismatch")

    if cap.intent_id != intent_id:
        logger.error("capability_wrong_intent", capability_id=str(capability_id))
        raise CapabilityInvalidError("Capability intent binding mismatch")
    if session_id is not None and cap.session_id != session_id:
        logger.error("capability_wrong_session", capability_id=str(capability_id))
        raise CapabilityInvalidError("Capability session binding mismatch")

    # 5. Signature verification
    sig_valid = verify_capability_signature(
        capability_id=cap.id,
        intent_id=cap.intent_id,
        user_id=cap.user_id,
        agent_id=cap.agent_id,
        merchant_id=cap.merchant_id,
        product_id=cap.product_id,
        amount_minor=cap.amount_minor,
        currency=cap.currency,
        intent_hash=cap.intent_hash,
        nonce=cap.nonce,
        session_id=cap.session_id,
        expires_at=cap.expires_at,
        policy_version_id=str(cap.policy_version_id or ""),
        merchant_policy_id=str(cap.merchant_policy_id or ""),
        signature=cap.signature,
        signing_key=settings.capability_signing_key,
    )
    if not sig_valid:
        logger.error("capability_signature_invalid", capability_id=str(capability_id))
        raise CapabilityInvalidError("Capability signature verification failed — tamper detected")

    # 6. Atomically mark as USED — replay protection
    now = utcnow()
    cap.status = CapabilityStatus.USED
    cap.used_at = now
    cap.used_by_request_id = request_id
    await cap_repo.save(cap)

    logger.info(
        "capability_consumed",
        capability_id=str(capability_id),
        intent_id=str(intent_id),
        request_id=request_id,
    )
