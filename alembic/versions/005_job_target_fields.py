"""add target fields to job

Revision ID: 005_job_target_fields
Revises: 004_node_encryption_key
Create Date: 2026-03-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "005_job_target_fields"
down_revision = "004_node_encryption_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job",
        sa.Column("target_type", sa.String(length=64), nullable=False, server_default="generic"),
    )
    op.add_column(
        "job",
        sa.Column("target_scope", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job", "target_scope")
    op.drop_column("job", "target_type")
