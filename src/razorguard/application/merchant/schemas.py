"""Merchant control plane Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from razorguard.shared.enums import (
    CampaignStatus,
    DiscountType,
    MerchantStatus,
    ProductAvailability,
)

# ── Merchant ──────────────────────────────────────────────


class MerchantResponse(BaseModel):
    merchant_id: uuid.UUID
    name: str
    display_name: str
    status: MerchantStatus
    razorpay_merchant_id: str | None = None
    model_config = {"from_attributes": True}


# ── Merchant Policy ───────────────────────────────────────


class MerchantPolicyRequest(BaseModel):
    """Configure what AI agents are allowed to do for this merchant."""

    agent_commerce_enabled: bool = True
    max_autonomous_order_minor: int = Field(ge=1, default=1_000_000)
    max_discount_pct: int = Field(ge=0, le=100, default=10)
    max_agent_txns_per_day: int = Field(ge=1, default=100)
    allowed_agent_categories: list[str] = Field(default_factory=list)
    allowed_payment_methods: list[str] = Field(default=["UPI", "CARD"])
    refund_requires_human: bool = True


class MerchantPolicyResponse(BaseModel):
    policy_id: uuid.UUID
    merchant_id: uuid.UUID
    version: int
    agent_commerce_enabled: bool
    max_autonomous_order_minor: int
    max_discount_pct: int
    max_agent_txns_per_day: int
    allowed_agent_categories: list[str]
    allowed_payment_methods: list[str]
    refund_requires_human: bool
    is_current: bool
    model_config = {"from_attributes": True}


# ── Campaign ──────────────────────────────────────────────


class CreateCampaignRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    discount_type: DiscountType
    discount_value: int = Field(ge=1)
    max_discount_minor: int = Field(ge=0, default=0)
    eligible_categories: list[str] = Field(default_factory=list)
    eligible_product_ids: list[str] = Field(default_factory=list)
    max_uses_per_agent_per_day: int = Field(ge=1, default=100)
    max_total_uses: int = Field(ge=1, default=10000)
    valid_from: datetime
    valid_until: datetime


class CampaignResponse(BaseModel):
    campaign_id: uuid.UUID
    merchant_id: uuid.UUID
    code: str
    discount_type: DiscountType
    discount_value: int
    max_discount_minor: int
    eligible_categories: list[str]
    status: CampaignStatus
    valid_from: datetime
    valid_until: datetime
    total_uses: int
    model_config = {"from_attributes": True}


# ── Catalog ───────────────────────────────────────────────


class CreateProductRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=2000)
    category: str = Field(min_length=1, max_length=128)
    price_minor: int = Field(ge=1, description="Price in paise (integer, never float)")
    currency: str = Field(default="INR")
    agent_purchase_allowed: bool = True


class CatalogProductResponse(BaseModel):
    product_id: uuid.UUID
    merchant_id: uuid.UUID
    sku: str
    title: str
    category: str
    price_minor: int
    currency: str
    availability: ProductAvailability
    agent_purchase_allowed: bool
    eligible_campaign_ids: list[str]
    model_config = {"from_attributes": True}
