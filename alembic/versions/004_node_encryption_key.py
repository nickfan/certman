"""add encryption_public_key to node

Revision ID: 004_node_encryption_key
Revises: 003_job_uniqueness_and_nonce
Create Date: 2026-03-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "004_node_encryption_key"
down_revision = "003_job_uniqueness_and_nonce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "node",
        sa.Column("encryption_public_key", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("node", "encryption_public_key")
