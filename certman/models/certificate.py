from __future__ import annotations

from pydantic import BaseModel, Field


class CertificateRecord(BaseModel):
    certificate_id: str
    entry_name: str
    primary_domain: str
    domains: list[str] = Field(default_factory=list)
    issuer: str
    status: str