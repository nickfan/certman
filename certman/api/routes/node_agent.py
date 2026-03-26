from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from cryptography.hazmat.primitives import serialization

from certman.api.deps import get_job_service
from certman.api.schemas import ApiResponse, PollRequest, ResultReportRequest
from certman.config import resolve_runtime_path
from certman.db.engine import make_session_factory
from certman.db.models import NodeNonceORM, NodeORM
from certman.security.identity import load_ed25519_private_key
from certman.security.signing import SecurityError, sign_message, verify_message
from certman.services.job_service import JobService

router = APIRouter(prefix="/api/v1/node-agent", tags=["node-agent"])
NONCE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class ActiveNode:
    node_id: str
    public_key_pem: str


@router.post("/poll", response_model=ApiResponse)
def poll(payload: PollRequest, request: Request, service: JobService = Depends(get_job_service)) -> ApiResponse:
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

    assignment = service.claim_next_job(node_id=payload.node_id, include_unassigned=True)
    assignments: list[dict] = []
    if assignment is not None:
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
            {
                "job_id": assignment.job_id,
                "job_type": assignment.job_type,
                "bundle_url": f"/api/v1/node-agent/bundles/{assignment.job_id}",
                "bundle_signature": bundle_signature,
            }
        )

    return ApiResponse(success=True, data={"assignments": assignments, "min_agent_version": "0.1.0"})


@router.post("/result", response_model=ApiResponse)
def report_result(payload: ResultReportRequest, request: Request, service: JobService = Depends(get_job_service)) -> ApiResponse:
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
    return ApiResponse(success=True, data={"job_id": payload.job_id, "status": updated.status if updated else payload.status})


def _get_active_node(runtime, node_id: str) -> ActiveNode:
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        node = session.query(NodeORM).filter(NodeORM.node_id == node_id).first()
        if node is None or node.status != "active" or not node.public_key:
            raise HTTPException(status_code=401, detail={"code": "AUTH_NODE_NOT_APPROVED", "message": "node not approved"})
        return ActiveNode(node_id=node.node_id, public_key_pem=node.public_key)


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


def _result_payload_bytes(payload: ResultReportRequest) -> bytes:
    body = {
        "job_id": payload.job_id,
        "status": payload.status,
        "output": payload.output,
        "error": payload.error,
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")