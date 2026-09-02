"""commerce control records

Revision ID: b10f1d0aa001
Revises: a09e53ccd3b7
"""

from alembic import op
import sqlalchemy as sa

revision = "b10f1d0aa001"
down_revision = "a09e53ccd3b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("budget_reservations", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False), sa.Column("intent_id", sa.UUID(), sa.ForeignKey("intents.id"), nullable=False), sa.Column("amount_minor", sa.Integer(), nullable=False), sa.Column("currency", sa.String(8), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("released_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.UniqueConstraint("intent_id", name="uq_budget_reservation_intent"))
    op.create_index("ix_budget_reservations_user_id", "budget_reservations", ["user_id"])
    op.create_index("ix_budget_reservations_status", "budget_reservations", ["status"])
    op.create_table("checkout_quotes", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("intent_id", sa.UUID(), sa.ForeignKey("intents.id"), nullable=False), sa.Column("quote_hash", sa.String(64), nullable=False, unique=True), sa.Column("canonical_payload", sa.Text(), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.UniqueConstraint("intent_id", name="uq_checkout_quote_intent"))
    op.create_table("campaign_reservations", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id"), nullable=False), sa.Column("intent_id", sa.UUID(), sa.ForeignKey("intents.id"), nullable=False), sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id"), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.UniqueConstraint("intent_id", name="uq_campaign_reservation_intent"))
    op.create_table("checkout_handoffs", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("transaction_id", sa.UUID(), sa.ForeignKey("transactions.id"), nullable=False, unique=True), sa.Column("razorpay_order_id", sa.String(128), nullable=False, unique=True), sa.Column("status", sa.String(16), nullable=False), sa.Column("checkout_payload", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))


def downgrade() -> None:
    op.drop_table("checkout_handoffs")
    op.drop_table("campaign_reservations")
    op.drop_table("checkout_quotes")
    op.drop_table("budget_reservations")
