"""
Campaign model — merchant-configured discount/promotion rules.

Agents can ONLY apply campaigns from this pool.
They cannot invent discounts. Policy engine validates everything.
All monetary values are in paise (integer).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import CampaignStatus, DiscountType


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    discount_type: Mapped[DiscountType] = mapped_column(
        String(16),
        nullable=False,  # PERCENTAGE | FIXED
    )
    # For PERCENTAGE: value is percent (e.g. 10 = 10%)
    # For FIXED: value is paise (e.g. 50000 = ₹500)
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False)

    # Cap for percentage discounts (paise). 0 = no cap.
    max_discount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Eligibility — JSON-encoded lists. Empty = all.
    eligible_categories: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    eligible_product_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Usage limits
    max_uses_per_agent_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_total_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    total_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[CampaignStatus] = mapped_column(
        String(16), nullable=False, default=CampaignStatus.ACTIVE, index=True
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="campaigns")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Campaign code={self.code} type={self.discount_type} value={self.discount_value}>"
