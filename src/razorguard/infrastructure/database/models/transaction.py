"""
Transaction — the full lifecycle record of one purchase attempt.

One intent can have at most one non-terminal transaction.
Terminal states are immutable — no backwards transitions.
UNKNOWN must never be treated as FAILED or trigger a blind retry.
All monetary values in paise (integer, never float).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import TransactionStatus


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        # One active (non-terminal) transaction per intent at a time
        UniqueConstraint("idempotency_key", name="uq_transactions_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intents.id"), nullable=False, index=True
    )
    capability_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capabilities.id"), nullable=True
    )

    # Deterministic idempotency key — prevents duplicate charges
    # HMAC(intent_id + user_id + merchant_id + amount + nonce)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    status: Mapped[TransactionStatus] = mapped_column(
        String(32), nullable=False, default=TransactionStatus.CREATED, index=True
    )

    # Frozen financial values at execution time — immutable after AUTHORIZED
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")

    # Razorpay provider identifiers — populated after execution
    razorpay_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # State machine metadata
    # APPROVE / DENY / ASK_USER
    policy_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    policy_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Execution timestamps
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Optimistic locking — prevents stale worker execution
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Relationships
    intent: Mapped["Intent"] = relationship(back_populates="transactions")  # noqa: F821
    payment_attempts: Mapped[list["PaymentAttempt"]] = relationship(  # noqa: F821
        back_populates="transaction", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} status={self.status} amount={self.amount_minor}>"
