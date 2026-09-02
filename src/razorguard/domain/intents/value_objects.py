"""
Intent value objects — immutable, validated, canonical.

These represent the typed, business-meaningful fields of a
transaction proposal. All monetary values in paise (integer).

SECURITY:
- amount_minor is always an integer, never float
- currency is always validated against SUPPORTED_CURRENCIES
- All fields are frozen after creation (dataclass frozen=True)
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from razorguard.domain.intents.exceptions import InvalidIntentValueError
from razorguard.shared.constants import (
    MAX_AMOUNT_MINOR,
    MINOR_UNITS_PER_INR,
    SUPPORTED_CURRENCIES,
    SUPPORTED_PAYMENT_METHODS,
)
from razorguard.shared.enums import PaymentMethod, ProtocolSource


@dataclass(frozen=True)
class Money:
    """
    Immutable monetary value. Always integer paise.

    Never use float. Never use Decimal for storage.
    Paise are the atomic unit — no rounding errors possible.
    """

    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int):
            raise InvalidIntentValueError(
                f"amount_minor must be integer paise, got {type(self.amount_minor).__name__}"
            )
        if self.amount_minor < 0:
            raise InvalidIntentValueError(f"amount_minor cannot be negative: {self.amount_minor}")
        if self.amount_minor == 0:
            raise InvalidIntentValueError("amount_minor cannot be zero")
        if self.amount_minor > MAX_AMOUNT_MINOR:
            raise InvalidIntentValueError(
                f"amount_minor {self.amount_minor} exceeds maximum {MAX_AMOUNT_MINOR}"
            )
        if self.currency not in SUPPORTED_CURRENCIES:
            raise InvalidIntentValueError(
                f"Unsupported currency: {self.currency}. Supported: {SUPPORTED_CURRENCIES}"
            )

    @property
    def as_rupees(self) -> Decimal:
        """For display only — never use for calculations."""
        return Decimal(self.amount_minor) / Decimal(MINOR_UNITS_PER_INR)

    def __str__(self) -> str:
        return f"₹{self.as_rupees:.2f}"

    def subtract_discount(self, discount_minor: int) -> "Money":
        if discount_minor < 0:
            raise InvalidIntentValueError("Discount cannot be negative")
        if discount_minor >= self.amount_minor:
            raise InvalidIntentValueError(
                f"Discount {discount_minor} >= amount {self.amount_minor}"
            )
        return Money(amount_minor=self.amount_minor - discount_minor, currency=self.currency)


@dataclass(frozen=True)
class IntentProduct:
    """Canonical product binding — values come from catalog, NOT from LLM."""

    product_id: uuid.UUID
    merchant_id: uuid.UUID
    category: str
    quantity: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise InvalidIntentValueError(f"Quantity must be positive, got {self.quantity}")
        if not self.category.strip():
            raise InvalidIntentValueError("Category cannot be empty")


@dataclass(frozen=True)
class IntentContext:
    """Session and protocol context — for correlation and observability."""

    session_id: str
    request_id: str
    protocol_source: ProtocolSource
    payment_method: PaymentMethod

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise InvalidIntentValueError("session_id cannot be empty")
        if self.payment_method.value not in SUPPORTED_PAYMENT_METHODS:
            raise InvalidIntentValueError(f"Unsupported payment method: {self.payment_method}")
