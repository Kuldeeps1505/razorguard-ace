"""
Capability — short-lived, one-time, cryptographically-signed execution token.

The agent does NOT receive general payment authority.
It receives permission to execute THIS ONE specific transaction.

Binds: user + agent + intent + merchant + product + amount +
       currency + policy_version + session + expiry + nonce.

Changing any field invalidates the capability.
One-time use — replay is explicitly rejected.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import CapabilityStatus


class Capability(Base, TimestampMixin):
    __tablename__ = "capabilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Authorization bindings — ALL must match at execution time
    intent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intents.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_products.id"), nullable=False
    )

    # Frozen values at issuance — final validation compares these
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Policy version bindings
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_versions.id"), nullable=True
    )
    merchant_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchant_policies.id"), nullable=True
    )

    # Replay protection
    nonce: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Cryptographic signature — HMAC over all fields
    signature: Mapped[str] = mapped_column(String(64), nullable=False)

    # Lifecycle
    status: Mapped[CapabilityStatus] = mapped_column(
        String(16), nullable=False, default=CapabilityStatus.ACTIVE, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    intent: Mapped["Intent"] = relationship(back_populates="capabilities")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Capability id={self.id} status={self.status} intent={self.intent_id}>"
