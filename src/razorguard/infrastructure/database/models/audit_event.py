"""
AuditEvent — append-only decision trail.

Every important action produces an audit event.
Events are NEVER deleted or modified — append only.
Hash chaining makes tampering detectable.

Every event carries: event_id, timestamp, correlation_id,
actor, intent_id, transaction_id, action, result, reason.
"""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import AuditActor


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Correlation — trace the full chain
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    intent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intents.id"), nullable=True, index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True, index=True
    )
    capability_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capabilities.id"), nullable=True
    )

    # Who performed the action
    actor: Mapped[AuditActor] = mapped_column(String(32), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # What happened
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # e.g. intent.created | policy.evaluated | payment.submitted | webhook.received

    result: Mapped[str] = mapped_column(String(16), nullable=False)
    # e.g. SUCCESS | DENIED | BLOCKED | UNKNOWN

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Policy context at time of decision
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Hash chain — H(this_event_data + previous_event_hash)
    # Tampering with any event breaks the chain.
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Extra structured context (JSON)
    extra_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditEvent id={self.id} action={self.action} result={self.result}>"
