from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel):
    success: bool
    data: Any | None = None
    error: ErrorDetail | None = None


class IssueCertRequest(BaseModel):
    entry_name: str


class JobResponse(BaseModel):
    job_id: str
    job_type: str
    subject_id: str
    node_id: str | None = None
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    attempts: int = 0
    result: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionRequest(BaseModel):
    topic: str
    endpoint: str
    secret: str


class PollRequest(BaseModel):
    node_id: str
    timestamp: int
    nonce: str
    agent_version: str
    signature: str


class ResultReportRequest(BaseModel):
    node_id: str
    job_id: str
    status: Literal["completed", "failed"]
    output: str | None = None
    error: str | None = None
    timestamp: int
    nonce: str
    signature: str
