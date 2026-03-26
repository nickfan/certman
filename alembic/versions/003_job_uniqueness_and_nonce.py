"""add job unique constraint and node nonce table

Revision ID: 003_job_uniqueness_and_nonce
Revises: 002_webhooks
Create Date: 2026-03-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "003_job_uniqueness_and_nonce"
down_revision = "002_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ux_job_type_subject_status",
        "job",
        ["job_type", "subject_id", "status"],
        unique=True,
    )

    op.create_table(
        "node_nonce",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("node_id", "nonce", name="uq_node_nonce"),
    )
    op.create_index("ix_node_nonce_node_id", "node_nonce", ["node_id"])
    op.create_index("ix_node_nonce_created_at", "node_nonce", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_node_nonce_created_at", table_name="node_nonce")
    op.drop_index("ix_node_nonce_node_id", table_name="node_nonce")
    op.drop_table("node_nonce")
    op.drop_index("ux_job_type_subject_status", table_name="job")