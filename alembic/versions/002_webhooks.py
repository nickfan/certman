"""add webhook tables

Revision ID: 002_webhooks
Revises: 001_initial
Create Date: 2026-03-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "002_webhooks"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_subscription",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_webhook_subscription_topic", "webhook_subscription", ["topic"])

    op.create_table(
        "webhook_delivery",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("subscription_id", sa.String(length=64), nullable=False),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_webhook_delivery_subscription_id", "webhook_delivery", ["subscription_id"])
    op.create_index("ix_webhook_delivery_topic", "webhook_delivery", ["topic"])


def downgrade() -> None:
    op.drop_index("ix_webhook_delivery_topic", table_name="webhook_delivery")
    op.drop_index("ix_webhook_delivery_subscription_id", table_name="webhook_delivery")
    op.drop_table("webhook_delivery")

    op.drop_index("ix_webhook_subscription_topic", table_name="webhook_subscription")
    op.drop_table("webhook_subscription")