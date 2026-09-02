"""
IssueCapability use case.

Called after:  policy APPROVE/ASK_USER + consent GRANTED

Issues a short-lived, one-time, cryptographically-signed capability.
The capability binds: user + agent + intent + merchant + product +
                      amount + currency + policy_version + session +
                      expiry + nonce.

An agent does NOT receive general payment authority.
It receives permission for ONE specific bounded transaction.

SECURITY:
- Capability is only issued after both policy and consent are verified
- Nonce is cryptographically random — replay detection
- TTL is short (configurable, default 5 minutes)
- Signature covers ALL fields — tampering is detectable
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.commerce.budget import reserve_budget
from razorguard.application.consent.mandates import get_active_mandate_for_intent
from razorguard.domain.authorization.capability_signer import sign_capability
from razorguard.domain.intents.exceptions import IntentHashMismatchError
from razorguard.domain.intents.hashing import verify_intent_hash
from razorguard.infrastructure.database.models.capability import Capability
from razorguard.infrastructure.database.repositories.capability_repository import (
    CapabilityRepository,
)
from razorguard.infrastructure.database.repositories.intent_repository import IntentRepository
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.clock import is_expired, utcnow_plus
from razorguard.shared.config import get_settings
from razorguard.shared.enums import CapabilityStatus, TransactionStatus
from razorguard.shared.errors import (
    CapabilityInvalidError,
    IntentExpiredError,
)
from razorguard.shared.security import generate_id, generate_nonce

logger = get_logger(__name__)


async def issue_capability(
    *,
    intent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    request_id: str,
    session_id: str,
    session: AsyncSession,
) -> Capability:
    """
    Issue a one-time execution capability for a validated, consented intent.

    Preconditions (enforced by caller):
    - Policy has returned APPROVE or (ASK_USER + consent GRANTED)
    - Intent is not expired
    - Intent belongs to authenticated_user_id

    This function does the final binding and cryptographic signing.
    """
    settings = get_settings()
    intent_repo = IntentRepository(session)
    cap_repo = CapabilityRepository(session)

    # 1. Fetch intent — scoped to authenticated user
    intent = await intent_repo.get_by_id_for_user(intent_id, authenticated_user_id)
    if not intent:
        raise IntentExpiredError(str(intent_id))

    # 2. Expiry check
    if is_expired(intent.expires_at):
        raise IntentExpiredError(str(intent_id))

    # 3. Intent must be in a state that allows capability issuance
    status = TransactionStatus(intent.status)
    if status not in (
        TransactionStatus.POLICY_APPROVED,
        TransactionStatus.CONSENT_GRANTED,
    ):
        raise CapabilityInvalidError(
            f"Intent {intent_id} in state {status} cannot receive a capability"
        )

    # 4. Re-verify intent hash (TOCTOU defense)
    hash_valid = verify_intent_hash(
        stored_hash=intent.intent_hash,
        user_id=intent.user_id,
        agent_id=intent.agent_id,
        merchant_id=intent.merchant_id,
        product_id=intent.product_id,
        amount_minor=intent.final_amount_minor,
        currency=intent.currency,
        category=intent.category,
        session_id=intent.session_id,
        expires_at=intent.expires_at,
        payment_method=intent.payment_method,
        quantity=intent.quantity,
    )
    if not hash_valid:
        logger.error("intent_hash_mismatch_at_capability_issuance", intent_id=str(intent_id))
        raise IntentHashMismatchError(str(intent_id))

    # 5. Check no active capability already exists for this intent
    existing = await cap_repo.get_active_for_intent(intent_id)
    if existing:
        # Idempotent — return existing capability
        logger.info("capability_already_exists", intent_id=str(intent_id))
        return existing

    # 6. Generate capability fields
    cap_id = uuid.UUID(generate_id())
    nonce = generate_nonce(32)
    expires_at = utcnow_plus(seconds=settings.capability_ttl_seconds)
    # Reservation is created before capability persistence, in the same DB
    # transaction. A concurrent agent therefore cannot oversubscribe budget.
    from razorguard.infrastructure.database.repositories.agent_repository import AgentRepository
    delegation = await AgentRepository(session).get_active_delegation(intent.user_id, intent.agent_id)
    if not delegation:
        raise CapabilityInvalidError("Delegation revoked before capability issuance")
    mandate = await get_active_mandate_for_intent(intent=intent, session=session)
    daily_limit = (
        min(delegation.max_daily_spend_minor, mandate.max_daily_amount_minor)
        if mandate
        else delegation.max_daily_spend_minor
    )
    await reserve_budget(
        intent=intent, daily_limit_minor=daily_limit,
        expires_at=expires_at, session=session,
    )
    policy_version_id = str(intent.policy_version_id or "")
    merchant_policy_id = str(intent.merchant_policy_id or "")

    # 7. Sign the capability
    signature = sign_capability(
        capability_id=cap_id,
        intent_id=intent.id,
        user_id=intent.user_id,
        agent_id=intent.agent_id,
        merchant_id=intent.merchant_id,
        product_id=intent.product_id,
        amount_minor=intent.final_amount_minor,
        currency=intent.currency,
        intent_hash=intent.intent_hash,
        nonce=nonce,
        session_id=session_id,
        expires_at=expires_at,
        policy_version_id=policy_version_id,
        merchant_policy_id=merchant_policy_id,
        signing_key=settings.capability_signing_key,
    )

    # 8. Persist capability
    capability = Capability(
        id=cap_id,
        intent_id=intent.id,
        user_id=intent.user_id,
        agent_id=intent.agent_id,
        merchant_id=intent.merchant_id,
        product_id=intent.product_id,
        amount_minor=intent.final_amount_minor,
        currency=intent.currency,
        intent_hash=intent.intent_hash,
        policy_version_id=intent.policy_version_id,
        merchant_policy_id=intent.merchant_policy_id,
        nonce=nonce,
        session_id=session_id,
        request_id=request_id,
        signature=signature,
        status=CapabilityStatus.ACTIVE,
        expires_at=expires_at,
    )
    await cap_repo.save(capability)

    logger.info(
        "capability_issued",
        capability_id=str(cap_id),
        intent_id=str(intent_id),
        expires_at=expires_at.isoformat(),
    )
    return capability
