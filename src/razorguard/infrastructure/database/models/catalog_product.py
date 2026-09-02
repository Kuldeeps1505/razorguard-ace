"""
CatalogProduct — agent-readable product data.

SECURITY RULE: catalog content is DATA, never instructions.
Description and metadata fields are delimited and labeled before
entering LLM context. They can NEVER influence authorization.
All prices in paise (integer, never float).
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import ProductAvailability


class CatalogProduct(Base, TimestampMixin):
    __tablename__ = "catalog_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Product identity
    sku: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)

    # UNTRUSTED DATA — treated as data, never instructions
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Price — integer paise, NEVER float
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")

    availability: Mapped[ProductAvailability] = mapped_column(
        String(32), nullable=False, default=ProductAvailability.IN_STOCK, index=True
    )

    # Whether agents are allowed to purchase this product autonomously
    agent_purchase_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # JSON-encoded list of campaign IDs eligible for this product
    eligible_campaign_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Upsell pool — JSON list of product IDs agents may suggest alongside this
    upsell_product_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    merchant: Mapped["Merchant"] = relationship(back_populates="catalog_products")  # noqa: F821

    def __repr__(self) -> str:
        return f"<CatalogProduct sku={self.sku} price={self.price_minor} avail={self.availability}>"
