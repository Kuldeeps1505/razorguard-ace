"""
Agent model — an AI agent that acts on behalf of a user.

Agents are registered, credentialed, rate-limited, and revocable.
Agent credentials are NEVER stored in plaintext — only hashed.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin
from razorguard.shared.enums import AgentStatus


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Credential — hashed, never plaintext
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    status: Mapped[AgentStatus] = mapped_column(
        String(32), nullable=False, default=AgentStatus.ACTIVE, index=True
    )

    # Tool permissions — JSON-encoded list e.g. ["SEARCH","COMPARE","PROPOSE_PURCHASE"]
    allowed_tools: Mapped[str] = mapped_column(
        Text, nullable=False, default='["SEARCH","COMPARE","PROPOSE_PURCHASE"]'
    )

    # Abuse protection
    max_payment_attempts_per_hour: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_tool_calls_per_minute: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="agents")  # noqa: F821
    delegations: Mapped[list["Delegation"]] = relationship(back_populates="agent", lazy="select")  # noqa: F821
    intents: Mapped[list["Intent"]] = relationship(back_populates="agent", lazy="select")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Agent id={self.id} name={self.name} status={self.status}>"
