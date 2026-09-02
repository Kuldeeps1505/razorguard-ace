"""
Intent — a strongly-typed, immutable transaction proposal.

Once an intent reaches AUTHORIZED state, its core fields cannot change.
The intent_hash cryptographically binds all key fields.
Changing any field → different hash → authorization invalidated.

All monetary values in paise (integer, never float).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import PaymentMethod, ProtocolSource, TransactionStatus


class Intent(Base, TimestampMixin):
    __tablename__ = "intents"
    __table_args__ = (UniqueConstraint("intent_hash", name="uq_intents_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Principals
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False, index=True
    )

    # Session correlation
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Product — canonical values from catalog, NOT from LLM
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Amounts — paise, never float
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")

    payment_method: Mapped[PaymentMethod] = mapped_column(
        String(16), nullable=False, default=PaymentMethod.UPI
    )

    # Campaign applied (if any)
    applied_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True
    )

    # Authorization bindings — versions stored at time of intent creation
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_versions.id"), nullable=True
    )
    merchant_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchant_policies.id"), nullable=True
    )

    # Cryptographic binding — HMAC of all key fields
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Protocol source — observability only, no security decision based on this
    protocol_source: Mapped[ProtocolSource] = mapped_column(
        String(16), nullable=False, default=ProtocolSource.RAZORGUARD
    )

    # Lifecycle
    status: Mapped[TransactionStatus] = mapped_column(
        String(32), nullable=False, default=TransactionStatus.CREATED, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # LLM-provided reason — stored for audit, NEVER used for authorization
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship()  # noqa: F821
    agent: Mapped["Agent"] = relationship(back_populates="intents")  # noqa: F821
    merchant: Mapped["Merchant"] = relationship()  # noqa: F821
    product: Mapped["CatalogProduct"] = relationship()  # noqa: F821
    consents: Mapped[list["Consent"]] = relationship(back_populates="intent", lazy="select")  # noqa: F821
    capabilities: Mapped[list["Capability"]] = relationship(back_populates="intent", lazy="select")  # noqa: F821
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="intent", lazy="select")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Intent id={self.id} status={self.status} amount={self.final_amount_minor}>"
