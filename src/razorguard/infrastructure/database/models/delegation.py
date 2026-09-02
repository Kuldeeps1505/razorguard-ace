"""
Delegation — a user grants constrained authority to an agent.

This is NOT "agent = trusted".
This is "agent may act within these exact bounds, for this duration".
Revocation takes immediate effect.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import DelegationStatus


class Delegation(Base, TimestampMixin):
    __tablename__ = "delegations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[DelegationStatus] = mapped_column(
        String(16), nullable=False, default=DelegationStatus.ACTIVE, index=True
    )

    # Spending limits — paise, integer
    max_transaction_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    max_daily_spend_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    max_monthly_spend_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Approval threshold — transactions above this require user consent
    require_consent_above_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Allowed scope — JSON-encoded lists. Empty = all.
    allowed_categories: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    allowed_merchant_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    blocked_merchant_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    allowed_currencies: Mapped[str] = mapped_column(Text, nullable=False, default='["INR"]')

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship()  # noqa: F821
    agent: Mapped["Agent"] = relationship(back_populates="delegations")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Delegation user={self.user_id} agent={self.agent_id} status={self.status}>"
