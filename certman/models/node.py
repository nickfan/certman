from __future__ import annotations

from pydantic import BaseModel, Field


class NodeIdentityRecord(BaseModel):
    node_id: str
    node_type: str
    public_key_id: str
    allowed_targets: list[str] = Field(default_factory=list)
    allowed_certificates: list[str] = Field(default_factory=list)