"""
PaymentAttempt — one attempt to execute payment via Razorpay.

A transaction may have multiple attempts (bounded by MAX_PAYMENT_ATTEMPTS).
UNKNOWN outcome → reconciliation, never blind retry.
Amount stored as paise (integer, never float).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import PaymentStatus


class PaymentAttempt(Base, TimestampMixin):
    __tablename__ = "payment_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Razorpay identifiers
    razorpay_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Idempotency key sent to Razorpay
    provider_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    status: Mapped[PaymentStatus] = mapped_column(
        String(16), nullable=False, default=PaymentStatus.PENDING, index=True
    )

    # Amount — paise, must match transaction.amount_minor exactly
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")

    # Error information
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timing
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Reconciliation metadata
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciliation_source: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,  # "WEBHOOK" | "QUERY" | "MANUAL"
    )

    transaction: Mapped["Transaction"] = relationship(back_populates="payment_attempts")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<PaymentAttempt id={self.id} attempt={self.attempt_number} "
            f"status={self.status} amount={self.amount_minor}>"
        )
