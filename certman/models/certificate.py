from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class CertificateRecord(BaseModel):
    certificate_id: str
    entry_name: str
    primary_domain: str
    domains: list[str] = Field(default_factory=list)
    issuer: str
    status: str
    not_after: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))