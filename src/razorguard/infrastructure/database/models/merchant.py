"""
Merchant model — the seller principal.

Merchants configure what AI agents can do on their behalf:
which products are agent-buyable, max discounts, campaigns,
kill switch, etc.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import MerchantStatus


class Merchant(Base, TimestampMixin):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    razorpay_merchant_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    status: Mapped[MerchantStatus] = mapped_column(
        String(32), nullable=False, default=MerchantStatus.ACTIVE, index=True
    )

    # Relationships
    policies: Mapped[list["MerchantPolicy"]] = relationship(
        back_populates="merchant", lazy="select"
    )
    campaigns: Mapped[list["Campaign"]] = relationship(  # noqa: F821
        back_populates="merchant", lazy="select"
    )
    catalog_products: Mapped[list["CatalogProduct"]] = relationship(  # noqa: F821
        back_populates="merchant", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Merchant id={self.id} name={self.name}>"


class MerchantPolicy(Base, TimestampMixin):
    __tablename__ = "merchant_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Kill switch — one toggle stops ALL agent commerce for this merchant
    agent_commerce_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Limits — all monetary values in paise (integer, never float)
    max_autonomous_order_minor: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1_000_000,  # ₹10,000
    )
    max_discount_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=10)  # 10%
    max_agent_txns_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # JSON-encoded lists
    allowed_agent_categories: Mapped[str] = mapped_column(
        Text, nullable=False, default='["search","compare","checkout"]'
    )
    allowed_payment_methods: Mapped[str] = mapped_column(
        Text, nullable=False, default='["UPI","CARD"]'
    )

    refund_requires_human: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    merchant: Mapped["Merchant"] = relationship(back_populates="policies")

    def __repr__(self) -> str:
        return f"<MerchantPolicy merchant={self.merchant_id} v={self.version}>"
