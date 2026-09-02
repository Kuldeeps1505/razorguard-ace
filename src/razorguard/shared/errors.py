"""
Typed application errors.

Every error has a machine-readable code so clients can handle
them programmatically. Never return raw exception strings to clients.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RazorGuardError(Exception):
    """Base error for all RazorGuard exceptions."""

    message: str
    code: str = "RAZORGUARD_ERROR"
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ── Intent errors ─────────────────────────────────────────────


class InvalidIntentError(RazorGuardError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message=message, code="INVALID_INTENT", details=details)


class IntentExpiredError(RazorGuardError):
    def __init__(self, intent_id: str) -> None:
        super().__init__(
            message=f"Intent {intent_id} has expired",
            code="INTENT_EXPIRED",
            details={"intent_id": intent_id},
        )


class IntentImmutableError(RazorGuardError):
    def __init__(self, intent_id: str) -> None:
        super().__init__(
            message=f"Intent {intent_id} cannot be modified after authorization",
            code="INTENT_IMMUTABLE",
            details={"intent_id": intent_id},
        )


# ── Policy errors ─────────────────────────────────────────────


class PolicyDeniedError(RazorGuardError):
    def __init__(self, reason: str, policy_id: str = "", **details: Any) -> None:
        super().__init__(
            message=f"Policy denied: {reason}",
            code="POLICY_DENIED",
            details={"reason": reason, "policy_id": policy_id, **details},
        )


class PolicyUnavailableError(RazorGuardError):
    def __init__(self) -> None:
        super().__init__(
            message="Policy engine unavailable — failing closed",
            code="POLICY_UNAVAILABLE",
        )


# ── Capability errors ─────────────────────────────────────────


class CapabilityExpiredError(RazorGuardError):
    def __init__(self, capability_id: str) -> None:
        super().__init__(
            message=f"Capability {capability_id} has expired",
            code="CAPABILITY_EXPIRED",
            details={"capability_id": capability_id},
        )


class CapabilityRevokedError(RazorGuardError):
    def __init__(self, capability_id: str) -> None:
        super().__init__(
            message=f"Capability {capability_id} has been revoked",
            code="CAPABILITY_REVOKED",
            details={"capability_id": capability_id},
        )


class CapabilityReplayError(RazorGuardError):
    def __init__(self, capability_id: str) -> None:
        super().__init__(
            message=f"Capability {capability_id} has already been used",
            code="CAPABILITY_REPLAY",
            details={"capability_id": capability_id},
        )


class CapabilityInvalidError(RazorGuardError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Capability invalid: {reason}",
            code="CAPABILITY_INVALID",
            details={"reason": reason},
        )


# ── Consent errors ────────────────────────────────────────────


class ConsentRequiredError(RazorGuardError):
    def __init__(self, intent_id: str) -> None:
        super().__init__(
            message=f"User consent required for intent {intent_id}",
            code="CONSENT_REQUIRED",
            details={"intent_id": intent_id},
        )


class ConsentExpiredError(RazorGuardError):
    def __init__(self, consent_id: str) -> None:
        super().__init__(
            message=f"Consent {consent_id} has expired",
            code="CONSENT_EXPIRED",
            details={"consent_id": consent_id},
        )


# ── Payment errors ────────────────────────────────────────────


class PaymentUnknownError(RazorGuardError):
    """Payment submitted but outcome uncertain. Must reconcile, never retry."""

    def __init__(self, transaction_id: str, razorpay_order_id: str = "") -> None:
        super().__init__(
            message=(
                f"Payment outcome unknown for transaction {transaction_id}. "
                "Queued for reconciliation."
            ),
            code="PAYMENT_UNKNOWN",
            details={
                "transaction_id": transaction_id,
                "razorpay_order_id": razorpay_order_id,
            },
        )


class PaymentFailedError(RazorGuardError):
    def __init__(self, transaction_id: str, reason: str = "") -> None:
        super().__init__(
            message=f"Payment failed for transaction {transaction_id}: {reason}",
            code="PAYMENT_FAILED",
            details={"transaction_id": transaction_id, "reason": reason},
        )


class DuplicatePaymentError(RazorGuardError):
    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            message="Duplicate payment request",
            code="DUPLICATE_PAYMENT",
            details={"idempotency_key": idempotency_key},
        )


class ConcurrentExecutionError(RazorGuardError):
    def __init__(self, intent_id: str) -> None:
        super().__init__(
            message=f"Concurrent execution detected for intent {intent_id}",
            code="CONCURRENT_EXECUTION",
            details={"intent_id": intent_id},
        )


# ── Product / Merchant errors ─────────────────────────────────


class ProductUnavailableError(RazorGuardError):
    def __init__(self, product_id: str) -> None:
        super().__init__(
            message=f"Product {product_id} is unavailable",
            code="PRODUCT_UNAVAILABLE",
            details={"product_id": product_id},
        )


class PriceChangedError(RazorGuardError):
    def __init__(
        self,
        product_id: str,
        original_minor: int,
        current_minor: int,
    ) -> None:
        super().__init__(
            message=(
                f"Price changed for product {product_id}: "
                f"₹{original_minor/100:.2f} → ₹{current_minor/100:.2f}"
            ),
            code="PRICE_CHANGED",
            details={
                "product_id": product_id,
                "original_minor": original_minor,
                "current_minor": current_minor,
            },
        )


class MerchantUnavailableError(RazorGuardError):
    def __init__(self, merchant_id: str) -> None:
        super().__init__(
            message=f"Merchant {merchant_id} is unavailable or has disabled agent commerce",
            code="MERCHANT_UNAVAILABLE",
            details={"merchant_id": merchant_id},
        )


# ── Webhook errors ────────────────────────────────────────────


class InvalidWebhookError(RazorGuardError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Invalid webhook: {reason}",
            code="INVALID_WEBHOOK",
            details={"reason": reason},
        )


# ── Auth errors ───────────────────────────────────────────────


class UnauthorizedAgentError(RazorGuardError):
    def __init__(self, agent_id: str = "") -> None:
        super().__init__(
            message="Agent unauthorized or not registered",
            code="UNAUTHORIZED_AGENT",
            details={"agent_id": agent_id},
        )


class RateLimitExceededError(RazorGuardError):
    def __init__(self, scope: str) -> None:
        super().__init__(
            message=f"Rate limit exceeded for {scope}",
            code="RATE_LIMIT_EXCEEDED",
            details={"scope": scope},
        )


class StubAdapterBlockedError(RazorGuardError):
    """ACP/AP2 stubs must not run on the production authorization path."""

    def __init__(self, protocol: str) -> None:
        super().__init__(
            message=(
                f"Protocol adapter '{protocol}' is a STUB and is blocked "
                "outside demo/development mode"
            ),
            code="STUB_ADAPTER_BLOCKED",
            details={"protocol": protocol},
        )
