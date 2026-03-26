from __future__ import annotations

from hashlib import sha256
import hmac

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, HTTPException, Request, Response, status

from certman.api.schemas import ApiResponse, NodeRegisterRequest, NodeRegisterResponse
from certman.config import resolve_runtime_path
from certman.services.node_service import NodeService

router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])


@router.post(
    "/register",
    response_model=ApiResponse[NodeRegisterResponse],
    summary="Register node",
    description="Register a node identity by submitting an Ed25519 public key and a one-time registration token.",
    response_description="Registered node metadata and poll endpoint",
)
def register_node(payload: NodeRegisterRequest, request: Request, response: Response) -> ApiResponse[NodeRegisterResponse]:
    runtime = request.app.state.runtime
    expected_token = runtime.env.get("CERTMAN_NODE_REGISTRATION_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "REGISTER_TOKEN_NOT_CONFIGURED", "message": "registration token is not configured"},
        )
    if not hmac.compare_digest(payload.register_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID_REGISTRATION_TOKEN", "message": "invalid registration token"},
        )

    fingerprint = _validate_and_fingerprint_ed25519(payload.public_key)

    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    service = NodeService(db_path=db_path)
    try:
        result = service.register_node(
            node_id=payload.node_id,
            node_type=payload.node_type,
            public_key=payload.public_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT_NODE_ALREADY_REGISTERED", "message": str(exc)},
        ) from exc

    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return ApiResponse(
        success=True,
        data=NodeRegisterResponse(
            node_id=result.node_id,
            status=result.status,
            created=result.created,
            public_key_fingerprint=fingerprint,
            poll_endpoint="/api/v1/node-agent/poll",
        ),
    )


def _validate_and_fingerprint_ed25519(public_key_pem: str) -> str:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_PUBLIC_KEY", "message": "public_key is not valid PEM"},
        ) from exc

    if not isinstance(key, Ed25519PublicKey):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_PUBLIC_KEY_ALGORITHM", "message": "public_key must be Ed25519"},
        )

    raw_bytes = key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256(raw_bytes).hexdigest()
