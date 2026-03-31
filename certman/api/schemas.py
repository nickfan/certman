from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


PayloadT = TypeVar("PayloadT")


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable business error code", examples=["NOT_FOUND_JOB"])
    message: str = Field(description="Human-readable error message", examples=["job not found"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "NOT_FOUND_JOB",
                "message": "job not found",
            }
        }
    )


class ApiResponse(BaseModel, Generic[PayloadT]):
    success: bool = Field(description="Whether the request succeeded")
    data: PayloadT | None = Field(default=None, description="Response payload when success=true")
    error: ErrorDetail | None = Field(default=None, description="Structured error when success=false")


class IssueCertRequest(BaseModel):
    entry_name: str = Field(description="Configured certificate entry name", examples=["site-a"])

    model_config = ConfigDict(json_schema_extra={"example": {"entry_name": "site-a"}})


class JobResponse(BaseModel):
    job_id: str = Field(description="Unique job identifier", examples=["a1b2c3d4e5f6"])
    job_type: str = Field(description="Job type", examples=["issue"])
    subject_id: str = Field(description="Certificate entry name or other subject identifier", examples=["site-a"])
    target_type: str = Field(default="generic", description="Delivery target type", examples=["k8s-ingress"])
    target_scope: str | None = Field(default=None, description="Delivery/network scope", examples=["office-lan"])
    node_id: str | None = Field(default=None, description="Assigned node ID when claimed by agent", examples=["node-a"])
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = Field(
        description="Current job state"
    )
    attempts: int = Field(default=0, description="Number of claim/execute attempts", examples=[0])
    result: str | None = Field(default=None, description="Result payload for completed jobs", examples=["ok"])
    error: str | None = Field(default=None, description="Error message for failed jobs", examples=["dns challenge failed"])
    created_at: datetime = Field(description="Creation timestamp in UTC")
    updated_at: datetime = Field(description="Last status update timestamp in UTC")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "a1b2c3d4e5f6",
                "job_type": "issue",
                "subject_id": "site-a",
                "target_type": "generic",
                "target_scope": None,
                "node_id": None,
                "status": "queued",
                "attempts": 0,
                "result": None,
                "error": None,
                "created_at": "2026-03-26T10:00:00Z",
                "updated_at": "2026-03-26T10:00:00Z",
            }
        }
    )


class JobAcceptedResponse(BaseModel):
    job_id: str = Field(description="Created issue job ID", examples=["a1b2c3d4e5f6"])
    created: bool = Field(description="False when an existing queued issue job was reused", examples=[True])


class RenewJobAcceptedResponse(BaseModel):
    job_id: str = Field(description="Renew job ID", examples=["a1b2c3d4e5f6"])
    created: bool = Field(description="False when an existing queued renew job was reused", examples=[True])


class WebhookSubscriptionRequest(BaseModel):
    topic: str = Field(description="Subscribed event topic", examples=["job.completed"])
    endpoint: str = Field(description="Webhook target URL", examples=["https://ops.example.com/hook"])
    secret: str = Field(description="Shared secret used to sign delivery payloads", examples=["topsecret"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "topic": "job.completed",
                "endpoint": "https://ops.example.com/hook",
                "secret": "topsecret",
            }
        }
    )


class WebhookResponse(BaseModel):
    id: str = Field(description="Webhook subscription ID", examples=["sub123456789"])
    topic: str = Field(description="Subscribed topic", examples=["job.completed"])
    endpoint: str = Field(description="Webhook target URL", examples=["https://ops.example.com/hook"])
    status: str = Field(description="Subscription status", examples=["active"])
    created_at: datetime = Field(description="Creation timestamp in UTC")
    updated_at: datetime = Field(description="Last update timestamp in UTC")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "sub123456789",
                "topic": "job.completed",
                "endpoint": "https://ops.example.com/hook",
                "status": "active",
                "created_at": "2026-03-26T10:00:00Z",
                "updated_at": "2026-03-26T10:00:00Z",
            }
        }
    )


class WebhookCreatedResponse(BaseModel):
    id: str = Field(description="Created or updated subscription ID", examples=["sub123456789"])


class UpdateWebhookRequest(BaseModel):
    endpoint: str | None = Field(default=None, description="New webhook target URL", examples=["https://ops.example.com/v2/hook"])
    secret: str | None = Field(default=None, description="New shared secret", examples=["rotated-secret"])
    status: str | None = Field(default=None, description="New status value", examples=["inactive"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "endpoint": "https://ops.example.com/v2/hook",
                "status": "inactive",
            }
        }
    )


class DeleteResponse(BaseModel):
    deleted: bool = Field(description="Whether the resource was deleted", examples=[True])


class PollAssignmentResponse(BaseModel):
    job_id: str = Field(description="Assigned job ID", examples=["a1b2c3d4e5f6"])
    job_type: str = Field(description="Assigned job type", examples=["issue"])
    bundle_url: str = Field(description="Relative URL used by agent to fetch bundle metadata", examples=["/api/v1/node-agent/bundles/a1b2c3d4e5f6"])
    bundle_signature: str = Field(description="Server signature over the assignment payload", examples=["base64-signature"])
    bundle_token: str | None = Field(default=None, description="Short-lived bundle access token")
    bundle_token_expires_at: int | None = Field(default=None, description="Bundle token expiration unix timestamp")


class PollResponse(BaseModel):
    assignments: list[PollAssignmentResponse] = Field(description="Assignments claimed for the current poll")
    min_agent_version: str = Field(description="Minimum supported agent version", examples=["0.1.0"])


class ResultAckResponse(BaseModel):
    job_id: str = Field(description="Acknowledged job ID", examples=["a1b2c3d4e5f6"])
    status: Literal["completed", "failed"] = Field(description="Persisted terminal state")


class NodeRegisterResponse(BaseModel):
    node_id: str = Field(description="Registered node ID", examples=["node-a"])
    status: str = Field(description="Registration status", examples=["pending"])
    created: bool = Field(description="Whether the node record was newly created", examples=[True])
    public_key_fingerprint: str = Field(description="SHA-256 fingerprint of submitted Ed25519 public key")
    poll_endpoint: str = Field(description="Relative poll endpoint exposed by control plane", examples=["/api/v1/node-agent/poll"])
    # Echoed back when the node registered an encryption key;
    # None when no encryption_public_key was submitted.
    encryption_key_fingerprint: str | None = Field(
        default=None,
        description="SHA-256 fingerprint of submitted X25519 encryption public key, if provided",
    )


class PollRequest(BaseModel):
    node_id: str = Field(description="Unique node identifier", examples=["node-a"])
    timestamp: int = Field(description="Unix timestamp in seconds", examples=[1774519200])
    nonce: str = Field(description="Single-use nonce for replay protection", examples=["nonce-20260326-0001"])
    agent_version: str = Field(description="Agent version string", examples=["0.1.0"])
    signature: str = Field(description="Ed25519 signature over node_id/timestamp/nonce", examples=["base64-signature"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "node_id": "node-a",
                "timestamp": 1774519200,
                "nonce": "nonce-20260326-0001",
                "agent_version": "0.1.0",
                "signature": "base64-signature",
            }
        }
    )


class ResultReportRequest(BaseModel):
    node_id: str = Field(description="Reporting node identifier", examples=["node-a"])
    job_id: str = Field(description="Reported job ID", examples=["a1b2c3d4e5f6"])
    status: Literal["completed", "failed"] = Field(description="Terminal execution status")
    output: str | None = Field(default=None, description="Execution output when status=completed", examples=["certificate issued"])
    error: str | None = Field(default=None, description="Execution error when status=failed", examples=["provider timeout"])
    timestamp: int = Field(description="Unix timestamp in seconds", examples=[1774519205])
    nonce: str = Field(description="Single-use nonce for replay protection", examples=["nonce-20260326-0002"])
    signature: str = Field(description="Ed25519 signature over result payload", examples=["base64-signature"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "node_id": "node-a",
                "job_id": "a1b2c3d4e5f6",
                "status": "completed",
                "output": "certificate issued",
                "error": None,
                "timestamp": 1774519205,
                "nonce": "nonce-20260326-0002",
                "signature": "base64-signature",
            }
        }
    )


class NodeRegisterRequest(BaseModel):
    node_id: str = Field(description="Unique node identifier", examples=["node-a"])
    node_type: str = Field(default="agent", description="Node type label", examples=["agent"])
    public_key: str = Field(description="PEM-encoded Ed25519 public key (used for request signing)")
    register_token: str = Field(description="One-time node registration token", examples=["registration-token"])
    # Optional: submit X25519 public key at registration time.
    # When provided and the server has bundle_encryption=encrypt configured,
    # bundle responses will be ECIES-encrypted so private key material
    # is never transmitted in plaintext over the wire.
    encryption_public_key: str | None = Field(
        default=None,
        description="Optional PEM-encoded X25519 public key for bundle envelope encryption",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "node_id": "node-a",
                "node_type": "agent",
                "public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
                "register_token": "registration-token",
                "encryption_public_key": None,
            }
        }
    )


class ConfigEntryResponse(BaseModel):
    name: str
    description: str = ""
    primary_domain: str
    secondary_domains: list[str] = Field(default_factory=list)
    wildcard: bool = True
    dns_provider: str
    account_id: str | None = None
    target_type: str = "generic"
    target_scope: str | None = None
    delivery_targets: list[dict] = Field(default_factory=list)


class ConfigValidateRequest(BaseModel):
    entry_names: list[str] = Field(default_factory=list)
    validate_all: bool = False


class ConfigValidateResponse(BaseModel):
    ok: bool = True


class BundleResponse(BaseModel):
    job_id: str = Field(description="Assigned job ID", examples=["a1b2c3d4e5f6"])
    # Plaintext mode (bundle_encryption=none): bundle and hooks are populated,
    # envelope is None.
    bundle: dict | None = Field(default=None, description="Bundle payload (plaintext mode only)")
    hooks: list[dict] = Field(default_factory=list, description="Hook definitions (plaintext mode only)")
    # Encrypted mode (bundle_encryption=encrypt): envelope is populated,
    # bundle and hooks are None / empty.
    # The envelope contains {ephemeral_public_key, nonce, ciphertext} (base64-encoded).
    # Plaintext inside the envelope is JSON: {"bundle": {...}, "hooks": [...]}.
    # When compressed=True the JSON was gzip-compressed before encryption.
    envelope: dict | None = Field(default=None, description="ECIES envelope (encrypted mode only)")
    compressed: bool = Field(default=False, description="True when bundle JSON was gzip-compressed before encryption")
