"""User model — the human principal who owns spending policies and delegates to agents."""

import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from razorguard.infrastructure.database.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    agents: Mapped[list["Agent"]] = relationship(  # noqa: F821
        back_populates="user", lazy="select"
    )
    spending_policies: Mapped[list["SpendingPolicy"]] = relationship(  # noqa: F821
        back_populates="user", lazy="select"
    )
    intents: Mapped[list["Intent"]] = relationship(  # noqa: F821
        back_populates="user", lazy="select"
    )
    consents: Mapped[list["Consent"]] = relationship(  # noqa: F821
        back_populates="user", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
