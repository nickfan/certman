from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives import serialization

from certman.security.envelope import Envelope, decrypt_envelope
from certman.security.identity import load_ed25519_private_key, load_x25519_private_key, load_x25519_public_key
from certman.security.signing import sign_message


@dataclass(frozen=True)
class RegistrationOutcome:
    """
    Registration attempt result with failure classification.
    
    Attributes:
        success: True if registration succeeded (agent can now poll)
        retryable: True if failure is transient (network, server error)
                  False if failure is permanent (auth, conflict, bad request)
        code: HTTP status or error code for diagnosis
        message: Human-readable error description
    
    Failure Classification:
    - Non-retryable (agent should stop): 401 (auth), 403 (forbidden), 409 (conflict), 422 (invalid request)
    - Retryable (agent should retry): 429 (rate limit), 5xx (server error), network exceptions
    
    Exit Code Mapping (for orchestrators):
    - retryable=true -> exit 3 (k8s restartPolicy: OnFailure will retry)
    - retryable=false -> exit 2 (k8s restartPolicy: OnFailure won't retry)
    """
    success: bool
    retryable: bool
    code: str
    message: str


class NodePoller:
    """
    Agent-side orchestrator for server registration and certificate job polling.
    
    Startup Flow:
    1. If register_token is provided:
       a. Call ensure_registered() to register node with server
       b. Server returns 200/201 if approved (or duplicate registration)
       c. On failure: classify error as retryable or permanent
    2. Once registered (or not needing registration):
       a. Call poll() to fetch pending certificate jobs
       b. Sign request with Ed25519 private key for authenticity
       c. Return list of job assignments
    
    Token Handling:
    - register_token: One-time token for initial registration (env var CERTMAN_NODE_REGISTRATION_TOKEN)
    - After successful registration, token is no longer needed
    - Subsequent polls use only node_id + Ed25519 signature for identity
    
    Error Handling:
    - Permanent failures (401, 403, 409, 422): Stop polling, inform orchestrator (exit 2)
    - Transient failures (429, 5xx, network): Retry later via orchestrator (exit 3)
    """
    def __init__(
        self,
        *,
        endpoint: str,
        node_id: str,
        private_key_path: str | Path | None = None,
        public_key_path: str | Path | None = None,
        node_type: str = "agent",
        register_token: str | None = None,
        encryption_private_key_path: str | Path | None = None,
        encryption_public_key_path: str | Path | None = None,
    ):
        """
        Initialize agent poller.
        
        Args:
            endpoint: Server base URL (e.g., http://certman-server:8000)
            node_id: Unique agent identifier (e.g., node-a, edge-us-east-1)
            private_key_path: Ed25519 private key (auto-generated if missing)
            public_key_path: Corresponding public key (optional, can be derived)
            node_type: Label for server records (default: "agent")
            register_token: One-time registration token (from admin, env: CERTMAN_NODE_REGISTRATION_TOKEN)
            encryption_private_key_path: X25519 private key for bundle decryption (optional).
                When provided the poller will also submit the corresponding public key at
                registration time, and automatically decrypt ECIES-encrypted bundle responses.
            encryption_public_key_path: X25519 public key path (optional; derived from private key if absent).
        """
        self._endpoint = endpoint
        self._node_id = node_id
        self._private_key_path = Path(private_key_path) if private_key_path else None
        self._public_key_path = Path(public_key_path) if public_key_path else None
        self._node_type = node_type
        self._register_token = register_token
        self._encryption_private_key_path = Path(encryption_private_key_path) if encryption_private_key_path else None
        self._encryption_public_key_path = Path(encryption_public_key_path) if encryption_public_key_path else None
        self._last_registration = RegistrationOutcome(success=True, retryable=False, code="REGISTER_NOT_REQUIRED", message="registration not required")

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def last_registration(self) -> RegistrationOutcome:
        return self._last_registration

    def poll(self) -> list[dict]:
        if self._private_key_path is None or not self._private_key_path.exists():
            return []

        registration = self.ensure_registered()
        self._last_registration = registration
        if not registration.success:
            return []

        timestamp = int(datetime.now(timezone.utc).timestamp())
        nonce = uuid4().hex
        private_key = load_ed25519_private_key(self._private_key_path)
        signature = sign_message(
            private_key,
            node_id=self._node_id,
            timestamp=timestamp,
            nonce=nonce,
            payload=b"",
        )
        payload = {
            "node_id": self._node_id,
            "timestamp": timestamp,
            "nonce": nonce,
            "agent_version": "0.1.0",
            "signature": signature,
        }
        try:
            response = httpx.post(f"{self._endpoint.rstrip('/')}/api/v1/node-agent/poll", json=payload, timeout=10)
            if response.status_code != 200:
                return []
            return response.json().get("data", {}).get("assignments", [])
        except (httpx.HTTPError, ValueError):
            return []

    def fetch_bundle(self, *, job_id: str, bundle_url: str) -> dict | None:
        if self._private_key_path is None or not self._private_key_path.exists():
            return None

        timestamp = int(datetime.now(timezone.utc).timestamp())
        nonce = uuid4().hex
        private_key = load_ed25519_private_key(self._private_key_path)
        payload_bytes = self._job_payload_bytes(job_id)
        signature = sign_message(
            private_key,
            node_id=self._node_id,
            timestamp=timestamp,
            nonce=nonce,
            payload=payload_bytes,
        )

        endpoint = self._resolve_url(bundle_url)
        params = {
            "node_id": self._node_id,
            "timestamp": timestamp,
            "nonce": nonce,
            "signature": signature,
        }
        try:
            response = httpx.get(endpoint, params=params, timeout=10)
            if response.status_code != 200:
                return None
            data = response.json().get("data")
            if data is None:
                return None
            return self._maybe_decrypt_bundle(data)
        except (httpx.HTTPError, ValueError):
            return None

    def report_result(
        self,
        *,
        job_id: str,
        status: str,
        output: str | None = None,
        error: str | None = None,
    ) -> bool:
        if self._private_key_path is None or not self._private_key_path.exists():
            return False

        timestamp = int(datetime.now(timezone.utc).timestamp())
        nonce = uuid4().hex
        private_key = load_ed25519_private_key(self._private_key_path)

        body = {
            "job_id": job_id,
            "status": status,
            "output": output,
            "error": error,
        }
        payload_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = sign_message(
            private_key,
            node_id=self._node_id,
            timestamp=timestamp,
            nonce=nonce,
            payload=payload_bytes,
        )

        request_body = {
            "node_id": self._node_id,
            "job_id": job_id,
            "status": status,
            "output": output,
            "error": error,
            "timestamp": timestamp,
            "nonce": nonce,
            "signature": signature,
        }
        try:
            response = httpx.post(
                f"{self._endpoint.rstrip('/')}/api/v1/node-agent/result",
                json=request_body,
                timeout=10,
            )
            return response.status_code == 200
        except (httpx.HTTPError, ValueError):
            return False

    def ensure_registered(self) -> RegistrationOutcome:
        """
        Register agent node with server (first-time only).
        
        Workflow:
        1. If no register_token: Skip registration (assume already registered)
        2. If private key missing: Return failure (cannot sign requests)
        3. POST to /api/v1/nodes/register with:
           - node_id: Unique identifier
           - public_key: Ed25519 public key (PEM format)
           - register_token: One-time approval token
        
        Server Response Handling:
        - 200/201: Success (node now approved, no further registration needed)
        - 401/403: Auth failed (bad token, invalid key format) - non-retryable
        - 409: Conflict (node_id already registered) - non-retryable
        - 422: Unprocessable (invalid PEM, non-Ed25519 key) - non-retryable
        - 429, 5xx: Server issues - retryable
        
        Returns:
            RegistrationOutcome with success/retryable flags and diagnostic info
        """
        if not self._register_token:
            return RegistrationOutcome(success=True, retryable=False, code="REGISTER_NOT_REQUIRED", message="registration not required")
        if self._private_key_path is None or not self._private_key_path.exists():
            return RegistrationOutcome(success=False, retryable=False, code="REGISTER_MISSING_PRIVATE_KEY", message="private key missing")

        public_key_pem = self._resolve_public_key_pem()
        payload = {
            "node_id": self._node_id,
            "node_type": self._node_type,
            "public_key": public_key_pem,
            "register_token": self._register_token,
        }
        # If an X25519 encryption keypair is configured, include the public key so
        # the server can encrypt bundle responses (opt-in end-to-end encryption).
        enc_pem = self._resolve_encryption_public_key_pem()
        if enc_pem:
            payload["encryption_public_key"] = enc_pem
        try:
            response = httpx.post(f"{self._endpoint.rstrip('/')}/api/v1/nodes/register", json=payload, timeout=10)
            if response.status_code in (200, 201):
                return RegistrationOutcome(success=True, retryable=False, code="REGISTER_OK", message="registered")

            response_code = "REGISTER_REJECTED"
            response_message = f"register failed with status {response.status_code}"
            try:
                body = response.json()
                response_code = body.get("error", {}).get("code", response_code)
                response_message = body.get("error", {}).get("message", response_message)
            except ValueError:
                pass

            if response.status_code in (401, 403, 409, 422):
                return RegistrationOutcome(success=False, retryable=False, code=response_code, message=response_message)
            if response.status_code == 429 or response.status_code >= 500:
                return RegistrationOutcome(success=False, retryable=True, code=response_code, message=response_message)
            return RegistrationOutcome(success=False, retryable=True, code=response_code, message=response_message)
        except (httpx.HTTPError, ValueError):
            return RegistrationOutcome(success=False, retryable=True, code="REGISTER_NETWORK_ERROR", message="register request failed")

    def _resolve_public_key_pem(self) -> str:
        if self._public_key_path is not None and self._public_key_path.exists():
            return self._public_key_path.read_text(encoding="utf-8")

        private_key = load_ed25519_private_key(self._private_key_path)
        public_key = private_key.public_key()
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def _resolve_url(self, path_or_url: str) -> str:
        normalized = path_or_url.strip()
        if normalized.startswith("http://") or normalized.startswith("https://"):
            return normalized
        return f"{self._endpoint.rstrip('/')}/{normalized.lstrip('/')}"

    @staticmethod
    def _job_payload_bytes(job_id: str) -> bytes:
        return json.dumps({"job_id": job_id}, separators=(",", ":"), sort_keys=True).encode("utf-8")

    def _resolve_encryption_public_key_pem(self) -> str | None:
        """Return X25519 public key PEM if encryption keypair is configured."""
        if self._encryption_private_key_path is None or not self._encryption_private_key_path.exists():
            return None
        if self._encryption_public_key_path is not None and self._encryption_public_key_path.exists():
            return self._encryption_public_key_path.read_text(encoding="utf-8")
        # Derive public key from private key.
        priv = load_x25519_private_key(self._encryption_private_key_path)
        return priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def _maybe_decrypt_bundle(self, data: dict) -> dict:
        """Return data unchanged (plaintext) or decrypt envelope if present."""
        if "envelope" not in data or data["envelope"] is None:
            return data
        # Encrypted mode: decrypt using local X25519 private key.
        if self._encryption_private_key_path is None or not self._encryption_private_key_path.exists():
            # No local decryption key; return as-is so caller can handle the error.
            return data
        priv = load_x25519_private_key(self._encryption_private_key_path)
        env_dict = data["envelope"]
        envelope = Envelope(
            ephemeral_public_key=env_dict["ephemeral_public_key"],
            nonce=env_dict["nonce"],
            ciphertext=env_dict["ciphertext"],
        )
        plaintext = decrypt_envelope(priv, envelope)
        if data.get("compressed", False):
            plaintext = gzip.decompress(plaintext)
        inner = json.loads(plaintext.decode("utf-8"))
        # Merge job_id from outer envelope into decrypted payload.
        return {
            "job_id": data.get("job_id"),
            "bundle": inner.get("bundle"),
            "hooks": inner.get("hooks", []),
        }
