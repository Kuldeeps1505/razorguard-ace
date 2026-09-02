"""
SpendingPolicy — user-side spending rules evaluated by the policy engine.

Every version is immutable once created.
Capabilities reference a specific policy_version_id — so changing
policy after authorization is correctly tracked.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin


class SpendingPolicy(Base, TimestampMixin):
    __tablename__ = "spending_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    user: Mapped["User"] = relationship(back_populates="spending_policies")  # noqa: F821
    versions: Mapped[list["PolicyVersion"]] = relationship(back_populates="policy", lazy="select")

    def __repr__(self) -> str:
        return f"<SpendingPolicy id={self.id} user={self.user_id}>"


class PolicyVersion(Base, TimestampMixin):
    __tablename__ = "policy_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spending_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Rules — all monetary values in paise
    max_single_transaction_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_limit_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_limit_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    require_consent_above_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # JSON-encoded lists
    allowed_categories: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    allowed_merchant_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    blocked_merchant_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    allowed_payment_methods: Mapped[str] = mapped_column(
        Text, nullable=False, default='["UPI","CARD","NETBANKING"]'
    )
    allowed_currencies: Mapped[str] = mapped_column(Text, nullable=False, default='["INR"]')

    # Snapshot hash — verify policy hasn't been tampered with
    rules_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    policy: Mapped["SpendingPolicy"] = relationship(back_populates="versions")

    def __repr__(self) -> str:
        return f"<PolicyVersion policy={self.policy_id} v={self.version}>"
