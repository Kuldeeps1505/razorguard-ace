"""
Consent — explicit user approval for a specific intent.

Consent is bound to: intent_id + user_id + amount + merchant + product.
Approving ₹4,500 keyboard cannot authorize ₹14,500 laptop.
One-time use. Expires. Version-checked on execution.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import ConsentMode, ConsentStatus


class Consent(Base, TimestampMixin):
    __tablename__ = "consents"
    __table_args__ = (
        # Prevent duplicate consent for same intent
        UniqueConstraint("intent_id", "user_id", name="uq_consent_intent_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intents.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    mode: Mapped[ConsentMode] = mapped_column(
        String(32), nullable=False, default=ConsentMode.SINGLE_TRANSACTION
    )
    status: Mapped[ConsentStatus] = mapped_column(
        String(16), nullable=False, default=ConsentStatus.PENDING, index=True
    )

    # One-time token — atomic check prevents double-use
    consent_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    intent: Mapped["Intent"] = relationship(back_populates="consents")  # noqa: F821
    user: Mapped["User"] = relationship(back_populates="consents")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Consent id={self.id} status={self.status} intent={self.intent_id}>"


class ConsentMandate(Base, TimestampMixin):
    """
    UPI Reserve Pay mandate — user consents once, agent executes within limits.
    MVP: schema persisted, execution path documented but execution stubbed.
    Maps to Razorpay UPI Reserve Pay primitive.
    """

    __tablename__ = "consent_mandates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )

    # Limits — paise
    max_amount_per_txn_minor: Mapped[int] = mapped_column(nullable=False)
    max_daily_amount_minor: Mapped[int] = mapped_column(nullable=False)

    # JSON-encoded list
    allowed_categories: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[ConsentStatus] = mapped_column(
        String(16), nullable=False, default=ConsentStatus.APPROVED, index=True
    )

    def __repr__(self) -> str:
        return f"<ConsentMandate user={self.user_id} merchant={self.merchant_id}>"
