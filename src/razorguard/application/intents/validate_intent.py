"""
ValidateIntent — re-validation immediately before payment execution.

This is the TOCTOU (time-of-check / time-of-use) defense.

Checks:
1. Intent exists and belongs to authenticated user
2. Intent has not expired
3. Intent is not in a terminal state
4. Intent hash still matches (tamper detection)
5. Product still available at canonical price
6. Merchant still active
7. Price has not drifted

This must run immediately before capability issuance and again
immediately before payment execution.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.domain.intents.exceptions import IntentHashMismatchError
from razorguard.domain.intents.hashing import verify_intent_hash
from razorguard.infrastructure.database.models.intent import Intent
from razorguard.infrastructure.database.repositories.catalog_repository import CatalogRepository
from razorguard.infrastructure.database.repositories.intent_repository import IntentRepository
from razorguard.infrastructure.database.repositories.merchant_repository import MerchantRepository
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.clock import is_expired
from razorguard.shared.errors import (
    IntentExpiredError,
    MerchantUnavailableError,
    PriceChangedError,
    ProductUnavailableError,
)

logger = get_logger(__name__)


async def validate_intent_for_execution(
    *,
    intent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    session: AsyncSession,
) -> Intent:
    """
    Re-validate an intent immediately before payment execution.

    Returns the intent if all checks pass.
    Raises a typed error for any validation failure.
    """
    intent_repo = IntentRepository(session)
    catalog_repo = CatalogRepository(session)
    merchant_repo = MerchantRepository(session)

    # 1. Fetch — scoped to authenticated user (tenant isolation)
    intent = await intent_repo.get_by_id_for_user(intent_id, authenticated_user_id)
    if not intent:
        raise IntentExpiredError(str(intent_id))  # treat not-found same as expired

    # 2. Expiry check
    if is_expired(intent.expires_at):
        logger.warning("intent_expired_at_execution", intent_id=str(intent_id))
        raise IntentExpiredError(str(intent_id))

    # 3. Terminal state check
    from razorguard.shared.enums import TransactionStatus

    if TransactionStatus(intent.status).is_terminal:
        raise IntentExpiredError(str(intent_id))

    # 4. Hash verification — tamper detection
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
        logger.error("intent_hash_mismatch", intent_id=str(intent_id))
        raise IntentHashMismatchError(str(intent_id))

    # 5. Re-fetch canonical product (price drift / availability check)
    product = await catalog_repo.get_available_for_agent(
        product_id=intent.product_id,
        merchant_id=intent.merchant_id,
    )
    if not product:
        logger.warning("product_unavailable_at_execution", product_id=str(intent.product_id))
        raise ProductUnavailableError(str(intent.product_id))

    # 6. Price drift detection
    canonical_price = product.price_minor * intent.quantity
    if canonical_price != intent.amount_minor:
        logger.warning(
            "price_drift_detected",
            intent_id=str(intent_id),
            authorized_price=intent.amount_minor,
            current_price=canonical_price,
        )
        raise PriceChangedError(
            str(intent.product_id),
            original_minor=intent.amount_minor,
            current_minor=canonical_price,
        )

    # 7. Merchant still active
    merchant = await merchant_repo.get_active(intent.merchant_id)
    if not merchant:
        raise MerchantUnavailableError(str(intent.merchant_id))

    logger.info("intent_validated_for_execution", intent_id=str(intent_id))
    return intent
