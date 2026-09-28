"""allow historical terminal jobs and dedupe only queued jobs

Revision ID: 006_job_active_uniqueness
Revises: 005_job_target_fields
Create Date: 2026-09-28
"""

from __future__ import annotations

from alembic import op

revision = "006_job_active_uniqueness"
down_revision = "005_job_target_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_job_type_subject_status")
    op.execute("UPDATE job SET status = 'cancelled', error = COALESCE(error, 'normalized from abandoned recovery state') WHERE status IN ('stale', 'abandoned')")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_job_type_subject_queued ON job (job_type, subject_id) WHERE status = 'queued'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_job_type_subject_queued")
    op.create_index("ux_job_type_subject_status", "job", ["job_type", "subject_id", "status"], unique=True)
