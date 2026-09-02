"""
WebhookEvent — persisted record of every Razorpay webhook received.

Never trust a webhook without signature verification.
Every event is deduplicated by razorpay_event_id.
Handler is idempotent — duplicate delivery produces no state change.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from razorguard.infrastructure.database.base import Base, TimestampMixin


class WebhookEvent(Base, TimestampMixin):
    __tablename__ = "webhook_events"
    __table_args__ = (
        # Deduplication — same event ID from Razorpay must not process twice
        UniqueConstraint("razorpay_event_id", name="uq_webhook_razorpay_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Razorpay's unique event identifier — used for deduplication
    razorpay_event_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Associated identifiers (validated against our DB, not trusted from payload)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True, index=True
    )

    # Raw payload — stored for audit and replay investigation
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Signature verified before persisting
    signature_verified: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Processing state
    processing_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="RECEIVED",
        index=True,
        # RECEIVED | PROCESSED | IGNORED | FAILED
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamp from Razorpay payload — used for replay detection
    event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<WebhookEvent id={self.id} type={self.event_type} "
            f"status={self.processing_status}>"
        )
