"""
ReconciliationJob — background jobs that resolve UNKNOWN payment states.

UNKNOWN must never be treated as FAILED.
UNKNOWN must never trigger a blind retry.
Every UNKNOWN payment enters reconciliation — query Razorpay → resolve.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin


class ReconciliationJob(Base, TimestampMixin):
    __tablename__ = "reconciliation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id"),
        nullable=False,
        index=True,
    )
    payment_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_attempts.id"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PENDING",
        index=True,
        # PENDING | RUNNING | RESOLVED | FAILED | ABANDONED
    )

    # How many times we've queried Razorpay
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    # Outcome after resolution
    resolved_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # "COMPLETED" | "FAILED"

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_source: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,  # "WEBHOOK" | "QUERY" | "MANUAL"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Next retry time — exponential backoff
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transaction: Mapped["Transaction"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<ReconciliationJob id={self.id} txn={self.transaction_id} "
            f"status={self.status} attempts={self.attempt_count}>"
        )
