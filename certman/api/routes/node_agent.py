from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import gzip
import hmac
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from cryptography.hazmat.primitives import serialization

from certman.api.deps import get_job_service
from certman.api.schemas import ApiResponse, BundleResponse, PollAssignmentResponse, PollRequest, PollResponse, ResultAckResponse, ResultReportRequest
from certman.config import entry_domains
from certman.config import resolve_runtime_path
from certman.db.engine import make_session_factory
from certman.db.models import NodeNonceORM, NodeORM
from certman.security.envelope import encrypt_envelope
from certman.security.identity import load_ed25519_private_key, load_x25519_public_key
from certman.security.signing import SecurityError, sign_message, verify_message
from certman.services.cert_service import resolve_entry_cert_name
from certman.services.job_service import JobService
from certman.node_agent.subscribe_bus import subscription_event_bus

router = APIRouter(prefix="/api/v1/node-agent", tags=["node-agent"])
NONCE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class ActiveNode:
    node_id: str
    public_key_pem: str
    encryption_public_key_pem: str | None = None


@router.post(
    "/poll",
    response_model=ApiResponse[PollResponse],
    summary="Poll for assignments",
    description="Validate a signed agent heartbeat, store replay-protected nonce state, and optionally return claimed assignments for the requesting node.",
    response_description="Assignment list and minimum supported agent version",
)
def poll(payload: PollRequest, request: Request, service: JobService = Depends(get_job_service)) -> ApiResponse[PollResponse]:
    runtime = request.app.state.runtime
    node = _get_active_node(runtime, payload.node_id)
    public_key = serialization.load_pem_public_key(node.public_key_pem.encode("utf-8"))
    try:
        verify_message(
            public_key,
            payload.signature,
            node_id=payload.node_id,
            timestamp=payload.timestamp,
            nonce=payload.nonce,
            payload=b"",
        )
    except SecurityError as exc:
        raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID_SIGNATURE", "message": str(exc)}) from exc

    _store_nonce_or_conflict(runtime, payload.node_id, payload.nonce)
    _touch_node_last_seen(runtime, payload.node_id)

    return ApiResponse(success=True, data=_claim_assignment_payload(runtime, service=service, node_id=payload.node_id))


@router.post(
    "/subscribe",
    response_model=ApiResponse[PollResponse],
    summary="Subscribe and fetch assignments",
    description="Compatibility endpoint for push+pull hybrid mode. Reuses signed poll semantics.",
)
def subscribe(payload: PollRequest, request: Request, service: JobService = Depends(get_job_service)) -> ApiResponse[PollResponse]:
    runtime = request.app.state.runtime
    node = _get_active_node(runtime, payload.node_id)
    public_key = serialization.load_pem_public_key(node.public_key_pem.encode("utf-8"))
    try:
        verify_message(
            public_key,
            payload.signature,
            node_id=payload.node_id,
            timestamp=payload.timestamp,
            nonce=payload.nonce,
            payload=b"",
        )
    except SecurityError as exc:
        raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID_SIGNATURE", "message": str(exc)}) from exc

    _store_nonce_or_conflict(runtime, payload.node_id, payload.nonce)
    _touch_node_last_seen(runtime, payload.node_id)

    wait_seconds = min(120, max(0, int(request.query_params.get("wait_seconds", "25"))))
    response_payload = _claim_assignment_payload(runtime, service=service, node_id=payload.node_id)
    if response_payload.assignments:
        return ApiResponse(success=True, data=response_payload)

    rev = subscription_event_bus.revision()
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        subscription_event_bus.wait_for_update(last_seen_revision=rev, timeout_seconds=min(1.0, remaining))
        rev = subscription_event_bus.revision()
        response_payload = _claim_assignment_payload(runtime, service=service, node_id=payload.node_id)
        if response_payload.assignments:
            return ApiResponse(success=True, data=response_payload)

    return ApiResponse(success=True, data=response_payload)


@router.post(
    "/heartbeat",
    response_model=ApiResponse[PollResponse],
    summary="Heartbeat without claiming jobs",
    description="Update node liveness with signed heartbeat and nonce replay protection, without claiming assignments.",
)
def heartbeat(payload: PollRequest, request: Request, service: JobService = Depends(get_job_service)) -> ApiResponse[PollResponse]:
    del service
    runtime = request.app.state.runtime
    node = _get_active_node(runtime, payload.node_id)
    public_key = serialization.load_pem_public_key(node.public_key_pem.encode("utf-8"))
    try:
        verify_message(
            public_key,
            payload.signature,
            node_id=payload.node_id,
            timestamp=payload.timestamp,
            nonce=payload.nonce,
            payload=b"",
        )
    except SecurityError as exc:
        raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID_SIGNATURE", "message": str(exc)}) from exc

    _store_nonce_or_conflict(runtime, payload.node_id, payload.nonce)
    _touch_node_last_seen(runtime, payload.node_id)
    return ApiResponse(success=True, data=PollResponse(assignments=[], min_agent_version="0.1.0"))


@router.post(
    "/result",
    response_model=ApiResponse[ResultAckResponse],
    summary="Report assignment result",
    description="Validate a signed result report from an agent and persist the terminal job state.",
    response_description="Acknowledged job result",
)
def report_result(payload: ResultReportRequest, request: Request, service: JobService = Depends(get_job_service)) -> ApiResponse[ResultAckResponse]:
    runtime = request.app.state.runtime
    node = _get_active_node(runtime, payload.node_id)
    public_key = serialization.load_pem_public_key(node.public_key_pem.encode("utf-8"))
    body = _result_payload_bytes(payload)
    try:
        verify_message(
            public_key,
            payload.signature,
            node_id=payload.node_id,
            timestamp=payload.timestamp,
            nonce=payload.nonce,
            payload=body,
        )
    except SecurityError as exc:
        raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID_SIGNATURE", "message": str(exc)}) from exc

    _store_nonce_or_conflict(runtime, payload.node_id, payload.nonce)
    _touch_node_last_seen(runtime, payload.node_id)
    job = service.get_job(payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_JOB", "message": "job not found"})
    if job.status != "running":
        raise HTTPException(status_code=422, detail={"code": "SEMANTIC_INVALID_JOB_STATE", "message": "job is not running"})
    if job.node_id is not None and job.node_id != payload.node_id:
        raise HTTPException(status_code=401, detail={"code": "AUTH_NODE_NOT_ALLOWED", "message": "job does not belong to node"})

    updated = service.update_status(
        payload.job_id,
        status=payload.status,
        result=payload.output if payload.status == "completed" else None,
        error=payload.error if payload.status == "failed" else None,
    )
    return ApiResponse(
        success=True,
        data=ResultAckResponse(job_id=payload.job_id, status=updated.status if updated else payload.status),
    )


@router.post(
    "/callback",
    response_model=ApiResponse[ResultAckResponse],
    summary="Callback job result",
    description="Compatibility endpoint for webhook-style callback in push+pull mode. Reuses signed result semantics.",
)
def callback_result(payload: ResultReportRequest, request: Request, service: JobService = Depends(get_job_service)) -> ApiResponse[ResultAckResponse]:
    return report_result(payload=payload, request=request, service=service)


@router.get(
    "/bundles/{job_id}",
    response_model=ApiResponse[BundleResponse],
    summary="Download assignment bundle",
    description="Return certificate bundle files for a running node-assigned job after signature and replay verification.",
    response_description="Certificate files and hook definitions",
)
def download_bundle(
    job_id: str,
    request: Request,
    node_id: str = Query(..., description="Requesting node identifier"),
    timestamp: int = Query(..., description="Unix timestamp in seconds"),
    nonce: str = Query(..., description="Single-use nonce for replay protection"),
    signature: str = Query(..., description="Ed25519 signature over node_id/timestamp/nonce/job_id payload"),
    bundle_token: str | None = Query(None, description="Short-lived bundle token issued by poll response"),
    service: JobService = Depends(get_job_service),
) -> ApiResponse[BundleResponse]:
    runtime = request.app.state.runtime
    node = _get_active_node(runtime, node_id)
    public_key = serialization.load_pem_public_key(node.public_key_pem.encode("utf-8"))

    signed_payload = json.dumps({"job_id": job_id}, separators=(",", ":"), sort_keys=True).encode("utf-8")
    try:
        verify_message(
            public_key,
            signature,
            node_id=node_id,
            timestamp=timestamp,
            nonce=nonce,
            payload=signed_payload,
        )
    except SecurityError as exc:
        raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID_SIGNATURE", "message": str(exc)}) from exc

    _store_nonce_or_conflict(runtime, node_id, nonce)
    _touch_node_last_seen(runtime, node_id)

    if runtime.config.server and runtime.config.server.bundle_token_required:
        if not bundle_token:
            raise HTTPException(status_code=401, detail={"code": "AUTH_BUNDLE_TOKEN_REQUIRED", "message": "bundle token required"})
        token_ok, token_error = _verify_bundle_token(runtime, token=bundle_token, node_id=node_id, job_id=job_id)
        if not token_ok:
            raise HTTPException(status_code=401, detail={"code": token_error or "AUTH_INVALID_BUNDLE_TOKEN", "message": "invalid bundle token"})

    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_JOB", "message": "job not found"})
    if job.status != "running":
        raise HTTPException(status_code=422, detail={"code": "SEMANTIC_INVALID_JOB_STATE", "message": "job is not running"})
    if job.node_id is not None and job.node_id != node_id:
        raise HTTPException(status_code=401, detail={"code": "AUTH_NODE_NOT_ALLOWED", "message": "job does not belong to node"})

    bundle = _load_job_bundle_files(runtime, job.subject_id)
    hooks = [hook.model_dump() for hook in runtime.config.hooks]

    encryption_mode = (runtime.config.server.bundle_encryption if runtime.config.server else "none")
    if encryption_mode == "encrypt" and node.encryption_public_key_pem:
        plaintext = json.dumps({"bundle": bundle, "hooks": hooks}, ensure_ascii=False).encode("utf-8")
        compress = False
        # Check node-level compression preference stored as a side-channel:
        # we don't have per-node compress flag in DB, so we use server-side heuristic:
        # compress when plaintext > 4 KiB (certificate files are typically 3-6 KiB total).
        if len(plaintext) > 4096:
            plaintext = gzip.compress(plaintext, compresslevel=6)
            compress = True
        enc_pub = load_x25519_public_key_from_pem(node.encryption_public_key_pem)
        envelope = encrypt_envelope(enc_pub, plaintext)
        return ApiResponse(
            success=True,
            data=BundleResponse(
                job_id=job_id,
                bundle=None,
                hooks=[],
                envelope={
                    "ephemeral_public_key": envelope.ephemeral_public_key,
                    "nonce": envelope.nonce,
                    "ciphertext": envelope.ciphertext,
                },
                compressed=compress,
            ),
        )

    return ApiResponse(success=True, data=BundleResponse(job_id=job_id, bundle=bundle, hooks=hooks))


def _get_active_node(runtime, node_id: str) -> ActiveNode:
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        node = session.query(NodeORM).filter(NodeORM.node_id == node_id).first()
        if node is None or not node.public_key:
            raise HTTPException(status_code=401, detail={"code": "AUTH_NODE_NOT_APPROVED", "message": "node not approved"})
        if node.status == "disabled":
            raise HTTPException(status_code=403, detail={"code": "AUTH_NODE_DISABLED", "message": "node is disabled"})
        if node.status != "active":
            raise HTTPException(status_code=401, detail={"code": "AUTH_NODE_NOT_APPROVED", "message": "node not approved"})
        return ActiveNode(
            node_id=node.node_id,
            public_key_pem=node.public_key,
            encryption_public_key_pem=node.encryption_public_key,
        )


def _touch_node_last_seen(runtime, node_id: str) -> None:
    """
    Update node.last_seen with throttle window to reduce database write pressure.
    
    Implements adaptive throttling:
    - First poll: always update (last_seen_updated_at is None)
    - Subsequent polls: update only if 45+ seconds have elapsed since last update
    - Skipped updates are silent (no error); heartbeat visibility is maintained via less-frequent writes
    
    This reduces write contention without sacrificing operational insights:
    - Enables cluster health monitoring via last_seen (nodes online within 45s window)
    - Reduces SQLite write pressure in agent-heavy scenarios (typical: 1 poll per 30s per node)
    """
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    session_factory = make_session_factory(db_path)
    now = datetime.now(timezone.utc)
    throttle_window_seconds = 45
    
    with session_factory() as session:
        node = session.query(NodeORM).filter(NodeORM.node_id == node_id).first()
        if node is None:
            return
        
        # Check throttle: skip update if within throttle window
        if node.last_seen_updated_at is not None:
            last_updated_at = node.last_seen_updated_at
            if last_updated_at.tzinfo is None:
                # SQLite may return naive datetimes even for timezone=True columns.
                last_updated_at = last_updated_at.replace(tzinfo=timezone.utc)
            elapsed = (now - last_updated_at).total_seconds()
            if elapsed < throttle_window_seconds:
                return  # Within throttle window, skip update
        
        # Update last_seen and track update timestamp
        node.last_seen = now
        node.last_seen_updated_at = now
        node.updated_at = now
        session.commit()


def _store_nonce_or_conflict(runtime, node_id: str, nonce: str) -> None:
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=NONCE_TTL_SECONDS)
        session.query(NodeNonceORM).filter(NodeNonceORM.created_at < cutoff).delete(synchronize_session=False)
        try:
            session.add(NodeNonceORM(id=uuid4().hex[:12], node_id=node_id, nonce=nonce))
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail={"code": "CONFLICT_REPLAY", "message": "nonce already used"}) from exc


def _load_server_signing_key(runtime):
    path = resolve_runtime_path(runtime, runtime.config.server.signing_key_path or "")
    if not Path(path).exists():
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_SIGNING_KEY", "message": "missing server signing key"})
    return load_ed25519_private_key(path)


def _bundle_token_secret(runtime) -> bytes:
    key_path = resolve_runtime_path(runtime, runtime.config.server.signing_key_path or "")
    if not Path(key_path).exists():
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_SIGNING_KEY", "message": "missing server signing key"})
    return Path(key_path).read_bytes()


def _mint_bundle_token(runtime, *, node_id: str, job_id: str) -> tuple[str, int]:
    ttl = runtime.config.server.bundle_token_ttl_seconds if runtime.config.server else 300
    expires_at = int(datetime.now(timezone.utc).timestamp()) + max(30, ttl)
    payload_dict = {"node_id": node_id, "job_id": job_id, "exp": expires_at}
    payload_json = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("ascii").rstrip("=")
    signature = hmac.new(_bundle_token_secret(runtime), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}", expires_at


def _verify_bundle_token(runtime, *, token: str, node_id: str, job_id: str) -> tuple[bool, str | None]:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        return False, "AUTH_INVALID_BUNDLE_TOKEN"

    expected_signature = hmac.new(
        _bundle_token_secret(runtime), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return False, "AUTH_INVALID_BUNDLE_TOKEN"

    padding = "=" * ((4 - len(payload_b64) % 4) % 4)
    try:
        payload_json = base64.urlsafe_b64decode((payload_b64 + padding).encode("ascii"))
        payload = json.loads(payload_json.decode("utf-8"))
    except Exception:
        return False, "AUTH_INVALID_BUNDLE_TOKEN"

    exp = int(payload.get("exp", 0))
    now = int(datetime.now(timezone.utc).timestamp())
    if exp < now:
        return False, "AUTH_BUNDLE_TOKEN_EXPIRED"
    if payload.get("node_id") != node_id or payload.get("job_id") != job_id:
        return False, "AUTH_BUNDLE_TOKEN_SCOPE_MISMATCH"
    return True, None


def _result_payload_bytes(payload: ResultReportRequest) -> bytes:
    body = {
        "job_id": payload.job_id,
        "status": payload.status,
        "output": payload.output,
        "error": payload.error,
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _claim_assignment_payload(runtime, *, service: JobService, node_id: str) -> PollResponse:
    assignment = service.claim_next_job(node_id=node_id, include_unassigned=True)
    assignments: list[PollAssignmentResponse] = []
    if assignment is not None:
        token, expires_at = _mint_bundle_token(runtime, node_id=node_id, job_id=assignment.job_id)
        server_signing_key = _load_server_signing_key(runtime)
        bundle_payload = assignment.model_dump_json().encode("utf-8")
        bundle_signature = sign_message(
            server_signing_key,
            node_id="server",
            timestamp=int(datetime.now(timezone.utc).timestamp()),
            nonce=uuid4().hex,
            payload=bundle_payload,
        )
        assignments.append(
            PollAssignmentResponse(
                job_id=assignment.job_id,
                job_type=assignment.job_type,
                bundle_url=f"/api/v1/node-agent/bundles/{assignment.job_id}",
                bundle_signature=bundle_signature,
                bundle_token=token,
                bundle_token_expires_at=expires_at,
            )
        )
    return PollResponse(assignments=assignments, min_agent_version="0.1.0")


def _load_job_bundle_files(runtime, entry_name: str) -> dict:
    target = [entry for entry in runtime.config.entries if entry.name == entry_name]
    if not target:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_ENTRY", "message": "entry not found"})
    entry = target[0]

    try:
        cert_name = resolve_entry_cert_name(runtime, entry, require_existing_lineage=False, resolution_mode="latest")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_BUNDLE", "message": str(exc)}) from exc

    base = runtime.paths.run_dir / runtime.config.global_.letsencrypt_dir / "live" / cert_name
    fullchain = base / "fullchain.pem"
    privkey = base / "privkey.pem"
    cert = base / "cert.pem"
    chain = base / "chain.pem"

    required_paths = [fullchain, privkey]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND_BUNDLE", "message": f"bundle files missing: {', '.join(missing)}"},
        )

    files = {
        "fullchain.pem": fullchain.read_text(encoding="utf-8"),
        "privkey.pem": privkey.read_text(encoding="utf-8"),
    }
    if cert.exists():
        files["cert.pem"] = cert.read_text(encoding="utf-8")
    if chain.exists():
        files["chain.pem"] = chain.read_text(encoding="utf-8")

    return {
        "entry_name": entry.name,
        "primary_domain": entry.primary_domain,
        "domains": entry_domains(entry),
        "target_type": entry.target_type,
        "target_scope": entry.target_scope,
        "delivery_options": {
            "mode": "render",
            "rollback_on_failure": True,
        } if entry.target_type == "k8s-ingress" else {},
        "files": files,
    }


def load_x25519_public_key_from_pem(pem: str):
    """Load an X25519 public key from a PEM string (not a file path)."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    key = serialization.load_pem_public_key(pem.encode("utf-8"))
    if not isinstance(key, X25519PublicKey):
        raise ValueError("encryption_public_key must be X25519")
    return key