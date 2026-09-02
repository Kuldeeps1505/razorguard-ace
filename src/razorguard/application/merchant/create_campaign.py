"""
CreateCampaign — merchant configures a discount/promotion campaign.

Agents can ONLY apply campaigns from this pool.
They cannot invent discounts. The policy engine validates eligibility.
All monetary values in paise (integer).
"""

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.merchant.schemas import CampaignResponse, CreateCampaignRequest
from razorguard.infrastructure.database.models.campaign import Campaign
from razorguard.infrastructure.database.repositories.merchant_repository import MerchantRepository
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.errors import InvalidIntentError, MerchantUnavailableError
from razorguard.shared.security import generate_id

logger = get_logger(__name__)


async def create_campaign(
    *,
    merchant_id: uuid.UUID,
    request: CreateCampaignRequest,
    session: AsyncSession,
) -> CampaignResponse:
    """Create a new campaign for a merchant."""
    merchant_repo = MerchantRepository(session)

    merchant = await merchant_repo.get_active(merchant_id)
    if not merchant:
        raise MerchantUnavailableError(str(merchant_id))

    # Validate campaign window
    if request.valid_until <= request.valid_from:
        raise InvalidIntentError("Campaign valid_until must be after valid_from")

    campaign = Campaign(
        id=uuid.UUID(generate_id()),
        merchant_id=merchant_id,
        code=request.code.upper(),
        discount_type=request.discount_type,
        discount_value=request.discount_value,
        max_discount_minor=request.max_discount_minor,
        eligible_categories=json.dumps(request.eligible_categories),
        eligible_product_ids=json.dumps(request.eligible_product_ids),
        max_uses_per_agent_per_day=request.max_uses_per_agent_per_day,
        max_total_uses=request.max_total_uses,
        valid_from=request.valid_from,
        valid_until=request.valid_until,
    )
    session.add(campaign)
    await session.flush()

    logger.info(
        "campaign_created",
        campaign_id=str(campaign.id),
        merchant_id=str(merchant_id),
        code=campaign.code,
    )

    return CampaignResponse(
        campaign_id=campaign.id,
        merchant_id=merchant_id,
        code=campaign.code,
        discount_type=campaign.discount_type,
        discount_value=campaign.discount_value,
        max_discount_minor=campaign.max_discount_minor,
        eligible_categories=json.loads(campaign.eligible_categories),
        status=campaign.status,
        valid_from=campaign.valid_from,
        valid_until=campaign.valid_until,
        total_uses=campaign.total_uses,
    )
