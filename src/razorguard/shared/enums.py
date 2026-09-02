"""
All application enums in one place.

Enums are the source of truth for valid states/types.
Never use raw strings where an enum exists.
"""

from enum import StrEnum


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


# ── Payment & Transaction ─────────────────────────────────────


class TransactionStatus(StrEnum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    POLICY_PENDING = "POLICY_PENDING"
    POLICY_APPROVED = "POLICY_APPROVED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    AWAITING_CONSENT = "AWAITING_CONSENT"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_REJECTED = "CONSENT_REJECTED"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    SUBMITTED = "SUBMITTED"  # Razorpay order exists; capture is unconfirmed
    UNKNOWN = "UNKNOWN"  # NEVER blindly retry from this state
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    AGENT_STOPPED = "AGENT_STOPPED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset(
    [
        TransactionStatus.COMPLETED,
        TransactionStatus.FAILED,
        TransactionStatus.POLICY_BLOCKED,
        TransactionStatus.CONSENT_REJECTED,
        TransactionStatus.EXPIRED,
        TransactionStatus.CANCELLED,
        TransactionStatus.AGENT_STOPPED,
    ]
)


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    REFUNDED = "REFUNDED"


class PolicyDecision(StrEnum):
    APPROVE = "APPROVE"
    DENY = "DENY"
    ASK_USER = "ASK_USER"


class ConsentMode(StrEnum):
    SINGLE_TRANSACTION = "SINGLE_TRANSACTION"  # MVP — per-intent approval
    MANDATE = "MANDATE"  # UPI Reserve Pay path


class ConsentStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    USED = "USED"


class CapabilityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    USED = "USED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


# ── Agent & Identity ──────────────────────────────────────────


class AgentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class DelegationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


# ── Merchant ──────────────────────────────────────────────────


class MerchantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


class CampaignStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    EXHAUSTED = "EXHAUSTED"
    EXPIRED = "EXPIRED"


class ProductAvailability(StrEnum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    DISCONTINUED = "DISCONTINUED"


class DiscountType(StrEnum):
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"


# ── Protocol ──────────────────────────────────────────────────


class ProtocolSource(StrEnum):
    RAZORGUARD = "RAZORGUARD"
    ACP = "ACP"  # Agentic Commerce Protocol (OpenAI + Stripe)
    AP2 = "AP2"  # Agent Payments Protocol (Google → FIDO)
    UAP = "UAP"  # Unified Agent Protocol (NPCI)
    UNKNOWN = "UNKNOWN"


# ── Payment method ────────────────────────────────────────────


class PaymentMethod(StrEnum):
    UPI = "UPI"
    CARD = "CARD"
    NETBANKING = "NETBANKING"


# ── Audit ────────────────────────────────────────────────────


class AuditActor(StrEnum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"
    POLICY_ENGINE = "POLICY_ENGINE"
    PAYMENT_PROVIDER = "PAYMENT_PROVIDER"
    MERCHANT = "MERCHANT"
