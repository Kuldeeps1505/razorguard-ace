"""
Unit tests — Phase 2 domain model invariants.

These tests verify model structure and business rules
without requiring a real database connection.
"""

from razorguard.shared.enums import (
    ConsentMode,
    DiscountType,
    PaymentMethod,
    PolicyDecision,
    ProtocolSource,
    TransactionStatus,
)

# ── TransactionStatus terminal state rules ────────────────


class TestTransactionTerminalStates:
    def test_completed_is_terminal(self):
        assert TransactionStatus.COMPLETED.is_terminal

    def test_failed_is_terminal(self):
        assert TransactionStatus.FAILED.is_terminal

    def test_policy_blocked_is_terminal(self):
        assert TransactionStatus.POLICY_BLOCKED.is_terminal

    def test_expired_is_terminal(self):
        assert TransactionStatus.EXPIRED.is_terminal

    def test_cancelled_is_terminal(self):
        assert TransactionStatus.CANCELLED.is_terminal

    def test_agent_stopped_is_terminal(self):
        assert TransactionStatus.AGENT_STOPPED.is_terminal

    def test_unknown_is_not_terminal(self):
        """
        CRITICAL INVARIANT:
        UNKNOWN must never be terminal — it must go to reconciliation.
        Never treat UNKNOWN as FAILED. Never blind-retry UNKNOWN.
        """
        assert not TransactionStatus.UNKNOWN.is_terminal

    def test_executing_is_not_terminal(self):
        assert not TransactionStatus.EXECUTING.is_terminal

    def test_authorized_is_not_terminal(self):
        assert not TransactionStatus.AUTHORIZED.is_terminal

    def test_all_terminal_states_exhaustive(self):
        terminal = [s for s in TransactionStatus if s.is_terminal]
        assert set(terminal) == {
            TransactionStatus.COMPLETED,
            TransactionStatus.FAILED,
            TransactionStatus.POLICY_BLOCKED,
            TransactionStatus.CONSENT_REJECTED,
            TransactionStatus.EXPIRED,
            TransactionStatus.CANCELLED,
            TransactionStatus.AGENT_STOPPED,
        }


# ── Enum completeness ─────────────────────────────────────


class TestEnumCompleteness:
    def test_payment_method_upi_present(self):
        assert PaymentMethod.UPI in PaymentMethod

    def test_protocol_source_all_present(self):
        sources = {p.value for p in ProtocolSource}
        assert "RAZORGUARD" in sources
        assert "ACP" in sources
        assert "AP2" in sources
        assert "UAP" in sources

    def test_policy_decision_three_values(self):
        """Policy engine must return exactly one of three decisions — never a boolean."""
        decisions = list(PolicyDecision)
        assert len(decisions) == 3
        assert PolicyDecision.APPROVE in decisions
        assert PolicyDecision.DENY in decisions
        assert PolicyDecision.ASK_USER in decisions

    def test_consent_mode_values(self):
        assert ConsentMode.SINGLE_TRANSACTION in ConsentMode
        assert ConsentMode.MANDATE in ConsentMode

    def test_discount_type_values(self):
        assert DiscountType.PERCENTAGE in DiscountType
        assert DiscountType.FIXED in DiscountType


# ── Model import smoke test ───────────────────────────────


class TestModelImports:
    """Verify all models import without errors."""

    def test_import_user(self):
        from razorguard.infrastructure.database.models.user import User

        assert User.__tablename__ == "users"

    def test_import_agent(self):
        from razorguard.infrastructure.database.models.agent import Agent

        assert Agent.__tablename__ == "agents"

    def test_import_merchant(self):
        from razorguard.infrastructure.database.models.merchant import Merchant, MerchantPolicy

        assert Merchant.__tablename__ == "merchants"
        assert MerchantPolicy.__tablename__ == "merchant_policies"

    def test_import_campaign(self):
        from razorguard.infrastructure.database.models.campaign import Campaign

        assert Campaign.__tablename__ == "campaigns"

    def test_import_catalog_product(self):
        from razorguard.infrastructure.database.models.catalog_product import CatalogProduct

        assert CatalogProduct.__tablename__ == "catalog_products"

    def test_import_delegation(self):
        from razorguard.infrastructure.database.models.delegation import Delegation

        assert Delegation.__tablename__ == "delegations"

    def test_import_spending_policy(self):
        from razorguard.infrastructure.database.models.spending_policy import (
            PolicyVersion,
            SpendingPolicy,
        )

        assert SpendingPolicy.__tablename__ == "spending_policies"
        assert PolicyVersion.__tablename__ == "policy_versions"

    def test_import_intent(self):
        from razorguard.infrastructure.database.models.intent import Intent

        assert Intent.__tablename__ == "intents"

    def test_import_consent(self):
        from razorguard.infrastructure.database.models.consent import Consent, ConsentMandate

        assert Consent.__tablename__ == "consents"
        assert ConsentMandate.__tablename__ == "consent_mandates"

    def test_import_capability(self):
        from razorguard.infrastructure.database.models.capability import Capability

        assert Capability.__tablename__ == "capabilities"

    def test_import_transaction(self):
        from razorguard.infrastructure.database.models.transaction import Transaction

        assert Transaction.__tablename__ == "transactions"

    def test_import_payment(self):
        from razorguard.infrastructure.database.models.payment import PaymentAttempt

        assert PaymentAttempt.__tablename__ == "payment_attempts"

    def test_import_webhook(self):
        from razorguard.infrastructure.database.models.webhook_event import WebhookEvent

        assert WebhookEvent.__tablename__ == "webhook_events"

    def test_import_audit(self):
        from razorguard.infrastructure.database.models.audit_event import AuditEvent

        assert AuditEvent.__tablename__ == "audit_events"

    def test_import_reconciliation(self):
        from razorguard.infrastructure.database.models.reconciliation import ReconciliationJob

        assert ReconciliationJob.__tablename__ == "reconciliation_jobs"

    def test_all_models_registered_in_init(self):
        """All registered persistence entities must be exported from the models package."""
        import razorguard.infrastructure.database.models as m

        assert len(m.__all__) == 22


# ── Financial invariants ──────────────────────────────────


class TestFinancialInvariants:
    def test_paise_to_rupees(self):
        from decimal import Decimal

        from razorguard.shared.utils import paise_to_rupees

        assert paise_to_rupees(149900) == Decimal("1499.00")
        assert paise_to_rupees(100) == Decimal("1.00")
        assert paise_to_rupees(0) == Decimal("0")

    def test_rupees_to_paise(self):
        from decimal import Decimal

        from razorguard.shared.utils import rupees_to_paise

        assert rupees_to_paise(Decimal("1499.00")) == 149900
        assert rupees_to_paise(Decimal("1.00")) == 100

    def test_no_float_in_money_conversion(self):
        """Verify utils use Decimal, not float."""
        from decimal import Decimal

        from razorguard.shared.utils import paise_to_rupees

        result = paise_to_rupees(149900)
        assert isinstance(result, Decimal)
        assert not isinstance(result, float)
