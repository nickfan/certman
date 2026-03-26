from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class NodeIdentityRecord(BaseModel):
    node_id: str
    node_type: str
    public_key_id: str
    allowed_targets: list[str] = Field(default_factory=list)
    allowed_certificates: list[str] = Field(default_factory=list)
    status: str = "active"
    last_seen: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))