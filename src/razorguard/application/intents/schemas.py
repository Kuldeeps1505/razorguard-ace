"""
Intent Pydantic schemas — request/response contracts.

SECURITY:
- user_id is NEVER accepted from request body for authorization.
  It is always derived from the authenticated principal in the route.
- All amounts are integer paise (never float, never string).
- LLM-provided fields (reason) are stored for audit only,
  never used for authorization decisions.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from razorguard.shared.constants import (
    MAX_AMOUNT_MINOR,
    SUPPORTED_CURRENCIES,
    SUPPORTED_PAYMENT_METHODS,
)
from razorguard.shared.enums import PaymentMethod, ProtocolSource, TransactionStatus


class CreateIntentRequest(BaseModel):
    """
    Submitted by the buyer agent after product selection.

    user_id is NOT here — it comes from the authenticated JWT.
    The agent provides the product/merchant it wants to purchase.
    All canonical values are re-fetched from the catalog server-side.
    """

    agent_id: uuid.UUID
    session_id: str = Field(min_length=1, max_length=64)
    product_id: uuid.UUID
    merchant_id: uuid.UUID
    category: str = Field(min_length=1, max_length=128)
    quantity: int = Field(ge=1, le=100)

    # Amount proposed by the agent — will be re-validated against catalog
    amount_minor: int = Field(ge=1, le=MAX_AMOUNT_MINOR)
    currency: str = Field(min_length=3, max_length=8)
    payment_method: PaymentMethod = PaymentMethod.UPI

    # Optional campaign code — validated against merchant policy
    campaign_code: str | None = Field(default=None, max_length=64)

    # LLM-provided context — stored for audit, NEVER used for authorization
    reason: str | None = Field(default=None, max_length=500)

    # Protocol source — observability only
    protocol_source: ProtocolSource = ProtocolSource.RAZORGUARD

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        upper = v.strip().upper()
        if upper not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency: {v}")
        return upper

    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method(cls, v: str) -> str:
        upper = str(v).strip().upper()
        if upper not in SUPPORTED_PAYMENT_METHODS:
            raise ValueError(f"Unsupported payment method: {v}")
        return upper

    @field_validator("amount_minor")
    @classmethod
    def validate_amount_not_float(cls, v: int) -> int:
        if not isinstance(v, int):
            raise ValueError("amount_minor must be an integer (paise), never float")
        return v


class IntentResponse(BaseModel):
    """Public intent representation returned to the caller."""

    intent_id: uuid.UUID
    status: TransactionStatus
    intent_hash: str

    user_id: uuid.UUID
    agent_id: uuid.UUID
    merchant_id: uuid.UUID
    product_id: uuid.UUID
    category: str
    quantity: int

    amount_minor: int
    discount_minor: int
    final_amount_minor: int
    currency: str
    payment_method: PaymentMethod

    applied_campaign_id: uuid.UUID | None
    protocol_source: ProtocolSource

    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class IntentStatusResponse(BaseModel):
    """Lightweight status check response."""

    intent_id: uuid.UUID
    status: TransactionStatus
    is_expired: bool
    is_terminal: bool

    model_config = {"from_attributes": True}
