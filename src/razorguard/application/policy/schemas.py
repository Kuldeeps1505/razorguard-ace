"""
Policy application Pydantic schemas — request/response for evaluation and simulator.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from razorguard.shared.enums import PolicyDecision


class RuleResultSchema(BaseModel):
    rule_name: str
    passed: bool
    reason: str
    rule_value: str = ""
    actual_value: str = ""

    model_config = {"from_attributes": True}


class PolicyDecisionResponse(BaseModel):
    """Full policy decision — returned by /policy/evaluate and /policy/simulate."""

    decision: PolicyDecision
    reason: str
    rule_results: list[RuleResultSchema]
    blocking_rule: str | None
    policy_version_id: str | None
    merchant_policy_id: str | None
    evaluated_at: datetime | None

    model_config = {"from_attributes": True}


class PolicySimulateRequest(BaseModel):
    """
    Simulate a policy decision for any hypothetical transaction.
    Used by the Policy Simulator demo feature.

    Does NOT require a real intent to exist.
    Does NOT modify any state.
    """

    # Intent fields to simulate
    amount_minor: int = Field(ge=1, description="Amount in paise")
    currency: str = Field(default="INR")
    category: str = Field(min_length=1)
    merchant_id: uuid.UUID
    product_id: uuid.UUID
    payment_method: str = Field(default="UPI")
    quantity: int = Field(default=1, ge=1)

    # Current spending (for daily limit simulation)
    daily_spend_minor: int = Field(default=0, ge=0)
    monthly_spend_minor: int = Field(default=0, ge=0)

    # Policy overrides (optional — use authenticated user's policy if not provided)
    # When provided, simulates with custom limits without changing real policy
    override_max_single_transaction_minor: int | None = None
    override_daily_limit_minor: int | None = None
    override_require_consent_above_minor: int | None = None
    override_merchant_max_autonomous_order_minor: int | None = None
