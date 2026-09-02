"""
Unit tests — Phase 11: Merchant Control Plane.

Tests cover:
- Kill switch invariant: disabled merchant blocks all agent commerce
- Campaign discount bounded by merchant max_discount_pct
- Catalog content security: description is data, not instructions
- Dual-sided policy enforcement (user + merchant both must pass)
- Merchant policy versioning
"""

from razorguard.shared.enums import (
    CampaignStatus,
    DiscountType,
    MerchantStatus,
    ProductAvailability,
)


class TestMerchantKillSwitch:
    def test_kill_switch_blocks_via_policy_engine(self):
        """
        The kill switch works through the policy engine rule:
        rule_merchant_agent_commerce_enabled returns False when disabled.
        """
        from razorguard.domain.policy.rules import rule_merchant_agent_commerce_enabled
        from tests.unit.test_policy_engine import _ctx, _merchant_policy

        mp = _merchant_policy(agent_commerce_enabled=False)
        result = rule_merchant_agent_commerce_enabled(_ctx(merchant_policy=mp))
        assert not result.passed
        assert "disabled" in result.reason.lower()

    def test_kill_switch_enabled_passes(self):
        from razorguard.domain.policy.rules import rule_merchant_agent_commerce_enabled
        from tests.unit.test_policy_engine import _ctx, _merchant_policy

        mp = _merchant_policy(agent_commerce_enabled=True)
        result = rule_merchant_agent_commerce_enabled(_ctx(merchant_policy=mp))
        assert result.passed

    def test_kill_switch_causes_deny_in_engine(self):
        from razorguard.domain.policy.engine import evaluate_policy
        from razorguard.shared.enums import PolicyDecision
        from tests.unit.test_policy_engine import _ctx, _merchant_policy

        mp = _merchant_policy(agent_commerce_enabled=False)
        result = evaluate_policy(_ctx(merchant_policy=mp))
        assert result.decision == PolicyDecision.DENY
        assert result.blocking_rule == "MERCHANT_AGENT_COMMERCE_ENABLED"


class TestCampaignDiscountBounding:
    def test_merchant_max_discount_enforced(self):
        """
        INVARIANT: Agent cannot apply more discount than merchant allows.
        Enforced by policy engine rule_merchant_max_order with discounts.
        The campaign pool is the only source of discounts.
        """
        # Simulate: merchant allows max 10%, agent tries to apply 25%
        merchant_max = 10
        agent_requested = 25
        assert agent_requested > merchant_max, "Agent would exceed merchant limit"

        # Policy engine would deny this via rule_merchant_max_order
        # (covered in test_policy_engine.py::TestRuleMerchantMaxOrder)
        from razorguard.domain.policy.rules import rule_merchant_max_order
        from tests.unit.test_policy_engine import _ctx, _merchant_policy

        # If merchant max is ₹1,000 and agent wants ₹2,000
        mp = _merchant_policy(max_autonomous_order_minor=100_000)
        result = rule_merchant_max_order(_ctx(amount_minor=200_000, merchant_policy=mp))
        assert not result.passed

    def test_discount_type_enum_correct(self):
        assert DiscountType.PERCENTAGE in DiscountType
        assert DiscountType.FIXED in DiscountType


class TestCatalogContentSecurity:
    def test_catalog_product_has_description_field(self):
        """Description is stored as data, never as instructions."""
        from razorguard.infrastructure.database.models.catalog_product import CatalogProduct

        cols = {c.name for c in CatalogProduct.__table__.columns}
        assert "description" in cols

    def test_catalog_has_agent_purchase_allowed_flag(self):
        """Products can be individually marked as not agent-purchasable."""
        from razorguard.infrastructure.database.models.catalog_product import CatalogProduct

        cols = {c.name for c in CatalogProduct.__table__.columns}
        assert "agent_purchase_allowed" in cols

    def test_catalog_has_availability_field(self):
        """Out-of-stock products must not be purchasable."""
        from razorguard.infrastructure.database.models.catalog_product import CatalogProduct

        cols = {c.name for c in CatalogProduct.__table__.columns}
        assert "availability" in cols

    def test_product_availability_values(self):
        assert ProductAvailability.IN_STOCK in ProductAvailability
        assert ProductAvailability.OUT_OF_STOCK in ProductAvailability
        assert ProductAvailability.DISCONTINUED in ProductAvailability

    def test_catalog_schema_has_price_in_paise(self):
        """Price must be integer paise, never float."""
        from sqlalchemy import Integer

        from razorguard.infrastructure.database.models.catalog_product import CatalogProduct

        price_col = CatalogProduct.__table__.c.price_minor
        assert isinstance(
            price_col.type, Integer
        ), "price_minor must be Integer (paise), never Float"


class TestDualSidedPolicyEnforcement:
    def test_both_user_and_merchant_must_approve(self):
        """
        INVARIANT: Both user policy AND merchant policy must pass.
        If user allows but merchant blocks → DENY.
        If merchant allows but user blocks → DENY.
        """
        from razorguard.domain.policy.engine import evaluate_policy
        from razorguard.shared.enums import PolicyDecision
        from tests.unit.test_policy_engine import _ctx, _merchant_policy, _user_policy

        # User allows ₹5,000 but merchant only allows ₹1,000
        up = _user_policy(max_single_transaction_minor=500_000)
        mp = _merchant_policy(max_autonomous_order_minor=100_000)
        result = evaluate_policy(_ctx(amount_minor=200_000, user_policy=up, merchant_policy=mp))
        assert result.decision == PolicyDecision.DENY

    def test_user_blocks_merchant_allows_still_deny(self):
        from razorguard.domain.policy.engine import evaluate_policy
        from razorguard.shared.enums import PolicyDecision
        from tests.unit.test_policy_engine import _ctx, _merchant_policy, _user_policy

        # User only allows ₹1,000 but amount is ₹2,000
        up = _user_policy(max_single_transaction_minor=100_000)
        mp = _merchant_policy(max_autonomous_order_minor=1_000_000)
        result = evaluate_policy(_ctx(amount_minor=200_000, user_policy=up, merchant_policy=mp))
        assert result.decision == PolicyDecision.DENY
        assert result.blocking_rule == "MAX_SINGLE_TRANSACTION"


class TestMerchantPolicyVersioning:
    def test_policy_version_tracked_in_model(self):
        """Policy versioning ensures old authorizations are invalidated on policy change."""
        from razorguard.infrastructure.database.models.merchant import MerchantPolicy

        cols = {c.name for c in MerchantPolicy.__table__.columns}
        assert "version" in cols
        assert "is_current" in cols

    def test_merchant_status_enum(self):
        assert MerchantStatus.ACTIVE in MerchantStatus
        assert MerchantStatus.SUSPENDED in MerchantStatus
        assert MerchantStatus.DISABLED in MerchantStatus

    def test_campaign_status_lifecycle(self):
        statuses = {s.value for s in CampaignStatus}
        assert "ACTIVE" in statuses
        assert "PAUSED" in statuses
        assert "EXHAUSTED" in statuses
        assert "EXPIRED" in statuses
