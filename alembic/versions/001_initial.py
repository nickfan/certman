"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-03-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "certificate",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("entry_name", sa.String(length=128), nullable=False),
        sa.Column("primary_domain", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_certificate_entry_name", "certificate", ["entry_name"])
    op.create_index("ix_certificate_primary_domain", "certificate", ["primary_domain"])

    op.create_table(
        "job",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_status", "job", ["status"])

    op.create_table(
        "node",
        sa.Column("node_id", sa.String(length=128), primary_key=True),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("source_node_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_event_created_at", "audit_event", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_event_created_at", table_name="audit_event")
    op.drop_table("audit_event")

    op.drop_table("node")

    op.drop_index("ix_job_status", table_name="job")
    op.drop_table("job")

    op.drop_index("ix_certificate_primary_domain", table_name="certificate")
    op.drop_index("ix_certificate_entry_name", table_name="certificate")
    op.drop_table("certificate")
