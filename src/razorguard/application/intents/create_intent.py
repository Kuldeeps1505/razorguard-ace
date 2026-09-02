"""
CreateIntent use case.

Flow:
1. Validate schema (Pydantic, already done by route)
2. Authenticate agent
3. Fetch canonical product + merchant from catalog (NOT from LLM values)
4. Apply campaign if requested
5. Compute intent_hash
6. Check for duplicate (idempotency on intent_hash)
7. Persist intent
8. Emit audit event

SECURITY:
- user_id comes from authenticated JWT, never from request body
- canonical price/merchant come from DB, never from agent proposal
- LLM reason stored for audit only, never influences authorization
"""

import json
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.audit.record_event import record_audit_event
from razorguard.application.commerce.campaigns import reserve_campaign
from razorguard.application.intents.schemas import CreateIntentRequest, IntentResponse
from razorguard.domain.intents.hashing import hash_intent
from razorguard.domain.intents.value_objects import Money
from razorguard.infrastructure.database.models.campaign import Campaign
from razorguard.infrastructure.database.models.intent import Intent
from razorguard.infrastructure.database.repositories.agent_repository import AgentRepository
from razorguard.infrastructure.database.repositories.catalog_repository import CatalogRepository
from razorguard.infrastructure.database.repositories.intent_repository import IntentRepository
from razorguard.infrastructure.database.repositories.merchant_repository import MerchantRepository
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.clock import utcnow, utcnow_plus
from razorguard.shared.enums import AuditActor, CampaignStatus, DiscountType, TransactionStatus
from razorguard.shared.errors import (
    InvalidIntentError,
    MerchantUnavailableError,
    ProductUnavailableError,
    UnauthorizedAgentError,
)
from razorguard.shared.security import generate_id

logger = get_logger(__name__)

# Intent is valid for 10 minutes — capability will have shorter TTL
INTENT_TTL_SECONDS = 600


async def create_intent(
    *,
    request: CreateIntentRequest,
    authenticated_user_id: uuid.UUID,  # ALWAYS from JWT, never from request body
    session: AsyncSession,
) -> IntentResponse:
    """
    Create a new transaction intent.

    user_id is injected from the authenticated JWT — the agent
    cannot claim to act for a different user.
    """
    agent_repo = AgentRepository(session)
    catalog_repo = CatalogRepository(session)
    merchant_repo = MerchantRepository(session)
    intent_repo = IntentRepository(session)

    # 1. Verify agent is active and belongs to this user
    agent = await agent_repo.get_active(request.agent_id)
    if not agent:
        raise UnauthorizedAgentError(str(request.agent_id))
    if agent.user_id != authenticated_user_id:
        # Agent trying to act for a different user — tenant isolation violation
        logger.warning(
            "agent_user_mismatch",
            agent_id=str(request.agent_id),
            agent_owner=str(agent.user_id),
            requesting_user=str(authenticated_user_id),
        )
        raise UnauthorizedAgentError(str(request.agent_id))

    # 2. Verify active delegation exists
    delegation = await agent_repo.get_active_delegation(
        user_id=authenticated_user_id,
        agent_id=request.agent_id,
    )
    if not delegation:
        raise UnauthorizedAgentError(f"No active delegation for agent {request.agent_id}")

    # 3. Fetch CANONICAL merchant — never trust agent-provided values
    merchant = await merchant_repo.get_active(request.merchant_id)
    if not merchant:
        raise MerchantUnavailableError(str(request.merchant_id))

    # 4. Fetch CANONICAL product — price and availability from DB, not LLM
    product = await catalog_repo.get_available_for_agent(
        product_id=request.product_id,
        merchant_id=request.merchant_id,
    )
    if not product:
        raise ProductUnavailableError(str(request.product_id))

    # 5. Validate canonical amount — use catalog price, not agent-proposed price
    canonical_amount = product.price_minor * request.quantity
    if canonical_amount != request.amount_minor:
        logger.warning(
            "intent_amount_mismatch",
            proposed=request.amount_minor,
            canonical=canonical_amount,
            product_id=str(request.product_id),
        )
        raise InvalidIntentError(
            f"Amount mismatch: agent proposed {request.amount_minor} paise, "
            f"catalog price is {canonical_amount} paise",
        )

    # Validate Money value object (catches negatives, zero, too-large, bad currency)
    money = Money(amount_minor=canonical_amount, currency=request.currency)

    # 6. Resolve a merchant-configured campaign. The LLM can name a code but
    # cannot create a discount: eligibility, dates and use cap are canonical.
    discount_minor = 0
    applied_campaign_id = None
    if request.campaign_code:
        now = utcnow()
        campaign = await session.scalar(
            select(Campaign).where(
                Campaign.merchant_id == request.merchant_id,
                Campaign.code == request.campaign_code,
                Campaign.status == CampaignStatus.ACTIVE,
                Campaign.valid_from <= now,
                Campaign.valid_until >= now,
            )
        )
        if not campaign:
            raise InvalidIntentError("Campaign is unavailable or expired")
        categories = json.loads(campaign.eligible_categories)
        product_ids = json.loads(campaign.eligible_product_ids)
        if (categories and product.category not in categories) or (product_ids and str(product.id) not in product_ids):
            raise InvalidIntentError("Campaign is not eligible for this product")
        if campaign.discount_type == DiscountType.PERCENTAGE:
            discount_minor = canonical_amount * campaign.discount_value // 100
            if campaign.max_discount_minor:
                discount_minor = min(discount_minor, campaign.max_discount_minor)
        else:
            discount_minor = campaign.discount_value
        discount_minor = min(discount_minor, canonical_amount)
        # Atomic reservation ensures concurrent agent requests cannot exceed
        # the merchant's campaign-wide usage cap.
        reserved = await session.execute(
            update(Campaign)
            .where(Campaign.id == campaign.id, Campaign.total_uses < Campaign.max_total_uses)
            .values(total_uses=Campaign.total_uses + 1)
        )
        if not reserved.rowcount:
            raise InvalidIntentError("Campaign usage limit reached")
        applied_campaign_id = campaign.id

    final_amount = money.subtract_discount(discount_minor) if discount_minor > 0 else money

    # 7. Set expiry
    expires_at = utcnow_plus(seconds=INTENT_TTL_SECONDS)

    # 8. Compute intent_hash — cryptographic binding of all key fields
    intent_hash = hash_intent(
        user_id=authenticated_user_id,
        agent_id=request.agent_id,
        merchant_id=request.merchant_id,
        product_id=request.product_id,
        amount_minor=final_amount.amount_minor,
        currency=final_amount.currency,
        category=request.category,
        session_id=request.session_id,
        expires_at=expires_at,
        payment_method=request.payment_method.value,
        quantity=request.quantity,
    )

    # 9. Idempotency — if an intent with this hash already exists, return it
    existing = await intent_repo.get_by_hash(intent_hash)
    if existing:
        logger.info("intent_duplicate_detected", intent_hash=intent_hash)
        return _to_response(existing)

    # 10. Persist intent
    intent = Intent(
        id=uuid.UUID(generate_id()),
        user_id=authenticated_user_id,
        agent_id=request.agent_id,
        merchant_id=request.merchant_id,
        product_id=request.product_id,
        session_id=request.session_id,
        category=request.category,
        quantity=request.quantity,
        amount_minor=canonical_amount,
        discount_minor=discount_minor,
        final_amount_minor=final_amount.amount_minor,
        currency=final_amount.currency,
        payment_method=request.payment_method,
        applied_campaign_id=applied_campaign_id,
        intent_hash=intent_hash,
        protocol_source=request.protocol_source,
        status=TransactionStatus.CREATED,
        expires_at=expires_at,
        reason=request.reason,
    )
    await intent_repo.save(intent)
    if applied_campaign_id:
        await reserve_campaign(campaign_id=applied_campaign_id, intent_id=intent.id, agent_id=intent.agent_id, session=session)
    await record_audit_event(
        session=session, request_id=f"intent:{intent.id}", session_id=intent.session_id,
        actor=AuditActor.AGENT, actor_id=str(request.agent_id), action="intent.created",
        result="SUCCESS", intent_id=intent.id, reason="Canonical catalog values accepted",
        extra_data={"merchant_id": str(intent.merchant_id), "product_id": str(intent.product_id), "amount_minor": intent.final_amount_minor},
    )

    logger.info(
        "intent_created",
        intent_id=str(intent.id),
        user_id=str(authenticated_user_id),
        agent_id=str(request.agent_id),
        amount=final_amount.amount_minor,
        currency=final_amount.currency,
    )

    return _to_response(intent)


def _to_response(intent: Intent) -> IntentResponse:
    return IntentResponse(
        intent_id=intent.id,
        status=intent.status,
        intent_hash=intent.intent_hash,
        user_id=intent.user_id,
        agent_id=intent.agent_id,
        merchant_id=intent.merchant_id,
        product_id=intent.product_id,
        category=intent.category,
        quantity=intent.quantity,
        amount_minor=intent.amount_minor,
        discount_minor=intent.discount_minor,
        final_amount_minor=intent.final_amount_minor,
        currency=intent.currency,
        payment_method=intent.payment_method,
        applied_campaign_id=intent.applied_campaign_id,
        protocol_source=intent.protocol_source,
        expires_at=intent.expires_at,
        created_at=intent.created_at,
    )
