from __future__ import annotations

from pydantic import BaseModel


class JobRecord(BaseModel):
    job_id: str
    job_type: str
    subject_id: str
    status: str = "queued"
    attempts: int = 0