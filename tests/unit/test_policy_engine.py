"""
Unit tests — Phase 4: Policy Engine.

Every rule is unit-tested in isolation.
Engine composition is tested for APPROVE / DENY / ASK_USER paths.
Fail-closed behavior is tested.

These are the most important tests in the project:
policy engine bugs = money leaving without authorization.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from razorguard.domain.policy.context import (
    IntentEvaluationContext,
    MerchantPolicyContext,
    SpendingContext,
    UserPolicyContext,
)
from razorguard.domain.policy.decisions import POLICY_UNAVAILABLE
from razorguard.domain.policy.engine import evaluate_policy
from razorguard.domain.policy.rules import (
    rule_agent_active,
    rule_category_allowed,
    rule_consent_threshold,
    rule_currency_allowed,
    rule_daily_limit,
    rule_delegation_active,
    rule_max_single_transaction,
    rule_merchant_agent_commerce_enabled,
    rule_merchant_allowed,
    rule_merchant_max_order,
    rule_merchant_payment_method,
)
from razorguard.shared.enums import PolicyDecision

# ── Test context builders ─────────────────────────────────


def _merchant_policy(
    agent_commerce_enabled: bool = True,
    max_autonomous_order_minor: int = 1_000_000,
    max_discount_pct: int = 10,
    allowed_payment_methods: list[str] | None = None,
) -> MerchantPolicyContext:
    return MerchantPolicyContext(
        merchant_policy_id=uuid.uuid4(),
        policy_version=1,
        agent_commerce_enabled=agent_commerce_enabled,
        max_autonomous_order_minor=max_autonomous_order_minor,
        max_discount_pct=max_discount_pct,
        max_agent_txns_per_day=100,
        allowed_agent_categories=[],
        allowed_payment_methods=(
            ["UPI", "CARD"] if allowed_payment_methods is None else allowed_payment_methods
        ),
        refund_requires_human=True,
    )


def _user_policy(
    max_single_transaction_minor: int = 500_000,
    daily_limit_minor: int = 2_000_000,
    require_consent_above_minor: int = 200_000,
    allowed_categories: list[str] | None = None,
    allowed_merchant_ids: list[str] | None = None,
    blocked_merchant_ids: list[str] | None = None,
    allowed_currencies: list[str] | None = None,
) -> UserPolicyContext:
    return UserPolicyContext(
        policy_version_id=uuid.uuid4(),
        policy_version=1,
        max_single_transaction_minor=max_single_transaction_minor,
        daily_limit_minor=daily_limit_minor,
        monthly_limit_minor=0,
        require_consent_above_minor=require_consent_above_minor,
        allowed_categories=[] if allowed_categories is None else allowed_categories,
        allowed_merchant_ids=[] if allowed_merchant_ids is None else allowed_merchant_ids,
        blocked_merchant_ids=[] if blocked_merchant_ids is None else blocked_merchant_ids,
        allowed_payment_methods=["UPI", "CARD"],
        allowed_currencies=["INR"] if allowed_currencies is None else allowed_currencies,
    )


def _ctx(
    amount_minor: int = 149900,
    category: str = "electronics",
    payment_method: str = "UPI",
    currency: str = "INR",
    merchant_id: uuid.UUID | None = None,
    agent_active: bool = True,
    delegation_active: bool = True,
    daily_spend_minor: int = 0,
    user_policy: UserPolicyContext | None = None,
    merchant_policy: MerchantPolicyContext | None = None,
) -> IntentEvaluationContext:
    mid = merchant_id or uuid.uuid4()
    return IntentEvaluationContext(
        intent_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        merchant_id=mid,
        product_id=uuid.uuid4(),
        amount_minor=amount_minor,
        final_amount_minor=amount_minor,
        currency=currency,
        category=category,
        payment_method=payment_method,
        quantity=1,
        user_policy=user_policy or _user_policy(),
        merchant_policy=merchant_policy or _merchant_policy(),
        spending=SpendingContext(
            daily_spend_minor=daily_spend_minor,
            monthly_spend_minor=0,
        ),
        agent_active=agent_active,
        delegation_active=delegation_active,
        evaluated_at=datetime.now(UTC),
        request_id="test-req",
    )


# ── Individual rule tests ─────────────────────────────────


class TestRuleAgentActive:
    def test_active_passes(self):
        r = rule_agent_active(_ctx(agent_active=True))
        assert r.passed

    def test_inactive_fails(self):
        r = rule_agent_active(_ctx(agent_active=False))
        assert not r.passed
        assert r.rule_name == "AGENT_ACTIVE"


class TestRuleDelegationActive:
    def test_active_passes(self):
        r = rule_delegation_active(_ctx(delegation_active=True))
        assert r.passed

    def test_inactive_fails(self):
        r = rule_delegation_active(_ctx(delegation_active=False))
        assert not r.passed


class TestRuleMerchantKillSwitch:
    def test_enabled_passes(self):
        mp = _merchant_policy(agent_commerce_enabled=True)
        r = rule_merchant_agent_commerce_enabled(_ctx(merchant_policy=mp))
        assert r.passed

    def test_disabled_fails(self):
        """Kill switch — merchant can immediately stop all agent commerce."""
        mp = _merchant_policy(agent_commerce_enabled=False)
        r = rule_merchant_agent_commerce_enabled(_ctx(merchant_policy=mp))
        assert not r.passed
        assert "disabled" in r.reason.lower()


class TestRuleMerchantMaxOrder:
    def test_within_limit_passes(self):
        mp = _merchant_policy(max_autonomous_order_minor=500_000)
        r = rule_merchant_max_order(_ctx(amount_minor=149900, merchant_policy=mp))
        assert r.passed

    def test_exceeds_limit_fails(self):
        mp = _merchant_policy(max_autonomous_order_minor=100_000)  # ₹1,000 max
        r = rule_merchant_max_order(_ctx(amount_minor=200_000, merchant_policy=mp))  # ₹2,000
        assert not r.passed

    def test_exactly_at_limit_passes(self):
        mp = _merchant_policy(max_autonomous_order_minor=149900)
        r = rule_merchant_max_order(_ctx(amount_minor=149900, merchant_policy=mp))
        assert r.passed


class TestRuleMerchantPaymentMethod:
    def test_allowed_method_passes(self):
        mp = _merchant_policy(allowed_payment_methods=["UPI", "CARD"])
        r = rule_merchant_payment_method(_ctx(payment_method="UPI", merchant_policy=mp))
        assert r.passed

    def test_blocked_method_fails(self):
        mp = _merchant_policy(allowed_payment_methods=["UPI"])
        r = rule_merchant_payment_method(_ctx(payment_method="CARD", merchant_policy=mp))
        assert not r.passed

    def test_empty_allowed_list_passes_all(self):
        mp = _merchant_policy(allowed_payment_methods=[])
        r = rule_merchant_payment_method(_ctx(payment_method="NETBANKING", merchant_policy=mp))
        assert r.passed


class TestRuleMaxSingleTransaction:
    def test_within_limit_passes(self):
        up = _user_policy(max_single_transaction_minor=500_000)
        r = rule_max_single_transaction(_ctx(amount_minor=149900, user_policy=up))
        assert r.passed

    def test_exceeds_limit_fails(self):
        up = _user_policy(max_single_transaction_minor=100_000)
        r = rule_max_single_transaction(_ctx(amount_minor=200_000, user_policy=up))
        assert not r.passed

    def test_exactly_at_limit_passes(self):
        up = _user_policy(max_single_transaction_minor=149900)
        r = rule_max_single_transaction(_ctx(amount_minor=149900, user_policy=up))
        assert r.passed


class TestRuleDailyLimit:
    def test_within_limit_passes(self):
        up = _user_policy(daily_limit_minor=2_000_000)
        r = rule_daily_limit(_ctx(amount_minor=149900, daily_spend_minor=0, user_policy=up))
        assert r.passed

    def test_exceeds_remaining_fails(self):
        up = _user_policy(daily_limit_minor=200_000)
        # already spent ₹1,500, trying ₹1,499 → total ₹2,999 > ₹2,000
        r = rule_daily_limit(_ctx(amount_minor=149900, daily_spend_minor=150_000, user_policy=up))
        assert not r.passed

    def test_exactly_at_remaining_passes(self):
        up = _user_policy(daily_limit_minor=300_000)
        r = rule_daily_limit(_ctx(amount_minor=149900, daily_spend_minor=150_100, user_policy=up))
        assert r.passed


class TestRuleCategoryAllowed:
    def test_empty_allowlist_allows_all(self):
        up = _user_policy(allowed_categories=[])
        r = rule_category_allowed(_ctx(category="electronics", user_policy=up))
        assert r.passed

    def test_allowed_category_passes(self):
        up = _user_policy(allowed_categories=["electronics", "books"])
        r = rule_category_allowed(_ctx(category="electronics", user_policy=up))
        assert r.passed

    def test_blocked_category_fails(self):
        up = _user_policy(allowed_categories=["books"])
        r = rule_category_allowed(_ctx(category="electronics", user_policy=up))
        assert not r.passed

    def test_case_insensitive(self):
        up = _user_policy(allowed_categories=["Electronics"])
        r = rule_category_allowed(_ctx(category="electronics", user_policy=up))
        assert r.passed


class TestRuleMerchantAllowed:
    def test_empty_lists_passes(self):
        up = _user_policy(allowed_merchant_ids=[], blocked_merchant_ids=[])
        r = rule_merchant_allowed(_ctx(user_policy=up))
        assert r.passed

    def test_blocked_merchant_fails(self):
        mid = uuid.uuid4()
        up = _user_policy(blocked_merchant_ids=[str(mid)])
        r = rule_merchant_allowed(_ctx(merchant_id=mid, user_policy=up))
        assert not r.passed

    def test_not_in_allowlist_fails(self):
        mid = uuid.uuid4()
        other = uuid.uuid4()
        up = _user_policy(allowed_merchant_ids=[str(other)])
        r = rule_merchant_allowed(_ctx(merchant_id=mid, user_policy=up))
        assert not r.passed

    def test_in_allowlist_passes(self):
        mid = uuid.uuid4()
        up = _user_policy(allowed_merchant_ids=[str(mid)])
        r = rule_merchant_allowed(_ctx(merchant_id=mid, user_policy=up))
        assert r.passed


class TestRuleCurrencyAllowed:
    def test_inr_allowed(self):
        up = _user_policy(allowed_currencies=["INR"])
        r = rule_currency_allowed(_ctx(currency="INR", user_policy=up))
        assert r.passed

    def test_unlisted_currency_fails(self):
        up = _user_policy(allowed_currencies=["INR"])
        r = rule_currency_allowed(_ctx(currency="USD", user_policy=up))
        assert not r.passed

    def test_empty_list_allows_all(self):
        up = _user_policy(allowed_currencies=[])
        r = rule_currency_allowed(_ctx(currency="USD", user_policy=up))
        assert r.passed


class TestRuleConsentThreshold:
    def test_below_threshold_passes(self):
        up = _user_policy(require_consent_above_minor=200_000)
        r = rule_consent_threshold(_ctx(amount_minor=149900, user_policy=up))
        assert r.passed  # below ₹2,000

    def test_above_threshold_fails(self):
        up = _user_policy(require_consent_above_minor=100_000)
        r = rule_consent_threshold(_ctx(amount_minor=200_000, user_policy=up))
        assert not r.passed  # above ₹1,000 threshold

    def test_zero_threshold_always_requires_consent(self):
        up = _user_policy(require_consent_above_minor=0)
        r = rule_consent_threshold(_ctx(amount_minor=1, user_policy=up))
        assert not r.passed


# ── Engine composition tests ──────────────────────────────


class TestPolicyEngine:
    def test_all_rules_pass_returns_approve(self):
        result = evaluate_policy(_ctx(amount_minor=100))
        assert result.decision == PolicyDecision.APPROVE
        assert result.approved

    def test_inactive_agent_returns_deny(self):
        result = evaluate_policy(_ctx(agent_active=False))
        assert result.decision == PolicyDecision.DENY
        assert result.blocking_rule == "AGENT_ACTIVE"

    def test_merchant_kill_switch_returns_deny(self):
        mp = _merchant_policy(agent_commerce_enabled=False)
        result = evaluate_policy(_ctx(merchant_policy=mp))
        assert result.decision == PolicyDecision.DENY
        assert result.blocking_rule == "MERCHANT_AGENT_COMMERCE_ENABLED"

    def test_amount_exceeds_user_limit_returns_deny(self):
        up = _user_policy(max_single_transaction_minor=100_000)
        result = evaluate_policy(_ctx(amount_minor=200_000, user_policy=up))
        assert result.decision == PolicyDecision.DENY
        assert result.blocking_rule == "MAX_SINGLE_TRANSACTION"

    def test_amount_exceeds_merchant_limit_returns_deny(self):
        mp = _merchant_policy(max_autonomous_order_minor=100_000)
        result = evaluate_policy(_ctx(amount_minor=200_000, merchant_policy=mp))
        assert result.decision == PolicyDecision.DENY

    def test_above_consent_threshold_returns_ask_user(self):
        up = _user_policy(
            max_single_transaction_minor=1_000_000,
            require_consent_above_minor=100_000,
        )
        result = evaluate_policy(_ctx(amount_minor=200_000, user_policy=up))
        assert result.decision == PolicyDecision.ASK_USER
        assert result.needs_consent

    def test_deny_takes_precedence_over_ask_user(self):
        """If both DENY and ASK_USER conditions exist, DENY wins — hard rules first."""
        up = _user_policy(
            max_single_transaction_minor=100_000,  # will DENY
            require_consent_above_minor=50_000,  # would also ASK_USER
        )
        result = evaluate_policy(_ctx(amount_minor=200_000, user_policy=up))
        assert result.decision == PolicyDecision.DENY  # DENY beats ASK_USER

    def test_result_contains_all_rule_results(self):
        result = evaluate_policy(_ctx(amount_minor=100))
        assert len(result.rule_results) > 0
        rule_names = [r.rule_name for r in result.rule_results]
        assert "AGENT_ACTIVE" in rule_names
        assert "MAX_SINGLE_TRANSACTION" in rule_names

    def test_fail_closed_on_engine_exception(self):
        """If engine throws, it must return DENY — never APPROVE on error."""
        with patch(
            "razorguard.domain.policy.engine._evaluate",
            side_effect=RuntimeError("DB connection lost"),
        ):
            result = evaluate_policy(_ctx())
        assert result.decision == PolicyDecision.DENY
        assert result is POLICY_UNAVAILABLE

    def test_daily_limit_race_scenario(self):
        """
        Spending race: user has ₹500 left, agent requests ₹600.
        Daily limit must prevent this.
        """
        up = _user_policy(
            max_single_transaction_minor=1_000_000,
            daily_limit_minor=1_000_000,  # ₹10,000 daily limit
        )
        result = evaluate_policy(
            _ctx(
                amount_minor=600_00,  # ₹600
                daily_spend_minor=950_000,  # already spent ₹9,500
                user_policy=up,
            )
        )
        assert result.decision == PolicyDecision.DENY
        assert result.blocking_rule == "DAILY_LIMIT"

    def test_blocked_category_returns_deny(self):
        up = _user_policy(allowed_categories=["books"])
        result = evaluate_policy(_ctx(category="electronics", user_policy=up))
        assert result.decision == PolicyDecision.DENY
        assert result.blocking_rule == "CATEGORY_ALLOWED"

    def test_blocked_merchant_returns_deny(self):
        mid = uuid.uuid4()
        up = _user_policy(blocked_merchant_ids=[str(mid)])
        result = evaluate_policy(_ctx(merchant_id=mid, user_policy=up))
        assert result.decision == PolicyDecision.DENY
        assert result.blocking_rule == "MERCHANT_ALLOWED"

    def test_decision_is_deterministic(self):
        """Same inputs must always produce same decision."""
        ctx = _ctx(amount_minor=100)
        r1 = evaluate_policy(ctx)
        r2 = evaluate_policy(ctx)
        assert r1.decision == r2.decision
        assert r1.blocking_rule == r2.blocking_rule
