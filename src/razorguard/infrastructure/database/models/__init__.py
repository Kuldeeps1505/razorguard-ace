# Import all models here so Alembic autogenerate sees every table.
# Order matters — referenced tables must appear before referencing ones.

from razorguard.infrastructure.database.models.agent import Agent
from razorguard.infrastructure.database.models.audit_event import AuditEvent
from razorguard.infrastructure.database.models.campaign import Campaign
from razorguard.infrastructure.database.models.capability import Capability
from razorguard.infrastructure.database.models.catalog_product import CatalogProduct
from razorguard.infrastructure.database.models.commerce_controls import (
    BudgetReservation,
    CampaignReservation,
    CheckoutHandoff,
    CheckoutQuote,
)
from razorguard.infrastructure.database.models.consent import Consent, ConsentMandate
from razorguard.infrastructure.database.models.delegation import Delegation
from razorguard.infrastructure.database.models.intent import Intent
from razorguard.infrastructure.database.models.merchant import Merchant, MerchantPolicy
from razorguard.infrastructure.database.models.payment import PaymentAttempt
from razorguard.infrastructure.database.models.reconciliation import ReconciliationJob
from razorguard.infrastructure.database.models.spending_policy import PolicyVersion, SpendingPolicy
from razorguard.infrastructure.database.models.transaction import Transaction
from razorguard.infrastructure.database.models.user import User
from razorguard.infrastructure.database.models.webhook_event import WebhookEvent

__all__ = [
    "User",
    "Merchant",
    "MerchantPolicy",
    "Campaign",
    "CatalogProduct",
    "Agent",
    "SpendingPolicy",
    "PolicyVersion",
    "Delegation",
    "Intent",
    "Consent",
    "ConsentMandate",
    "BudgetReservation",
    "CheckoutQuote",
    "CampaignReservation",
    "CheckoutHandoff",
    "Capability",
    "Transaction",
    "PaymentAttempt",
    "WebhookEvent",
    "AuditEvent",
    "ReconciliationJob",
]
