"""
PolicyContext — all the data the policy engine needs to make a decision.

Built from verified DB data, never from LLM/request-body values.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UserPolicyContext:
    """Snapshot of the user's current spending policy version."""

    policy_version_id: uuid.UUID
    policy_version: int
    max_single_transaction_minor: int
    daily_limit_minor: int
    monthly_limit_minor: int
    require_consent_above_minor: int
    allowed_categories: list[str]
    allowed_merchant_ids: list[str]
    blocked_merchant_ids: list[str]
    allowed_payment_methods: list[str]
    allowed_currencies: list[str]


@dataclass(frozen=True)
class MerchantPolicyContext:
    """Snapshot of the merchant's current agent commerce policy."""

    merchant_policy_id: uuid.UUID
    policy_version: int
    agent_commerce_enabled: bool
    max_autonomous_order_minor: int
    max_discount_pct: int
    max_agent_txns_per_day: int
    allowed_agent_categories: list[str]
    allowed_payment_methods: list[str]
    refund_requires_human: bool


@dataclass(frozen=True)
class SpendingContext:
    """Current spend totals — fetched atomically before evaluation."""

    daily_spend_minor: int
    monthly_spend_minor: int


@dataclass(frozen=True)
class IntentEvaluationContext:
    """Everything the policy engine needs — assembled before evaluation."""

    # Intent fields (canonical, from DB)
    intent_id: uuid.UUID
    user_id: uuid.UUID
    agent_id: uuid.UUID
    merchant_id: uuid.UUID
    product_id: uuid.UUID
    amount_minor: int
    final_amount_minor: int
    currency: str
    category: str
    payment_method: str
    quantity: int

    # Policy contexts (from DB, current versions)
    user_policy: UserPolicyContext
    merchant_policy: MerchantPolicyContext
    spending: SpendingContext

    # Agent status
    agent_active: bool
    delegation_active: bool

    # Request context
    evaluated_at: datetime
    request_id: str
