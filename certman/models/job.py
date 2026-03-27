from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class JobRecord(BaseModel):
    job_id: str
    job_type: str
    subject_id: str
    target_type: str = "generic"
    target_scope: str | None = None
    node_id: str | None = None
    status: str = "queued"
    attempts: int = 0
    result: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))