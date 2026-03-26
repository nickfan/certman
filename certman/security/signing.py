from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519


class SecurityError(ValueError):
    pass


def sign_message(
    private_key: ed25519.Ed25519PrivateKey,
    *,
    node_id: str,
    timestamp: int,
    nonce: str,
    payload: bytes,
) -> str:
    message = _canonical_message(node_id=node_id, timestamp=timestamp, nonce=nonce, payload=payload)
    signature = private_key.sign(message)
    return base64.b64encode(signature).decode("ascii")


def verify_message(
    public_key: ed25519.Ed25519PublicKey,
    signature: str,
    *,
    node_id: str,
    timestamp: int,
    nonce: str,
    payload: bytes,
    now: datetime | None = None,
    max_skew_seconds: int = 60,
) -> bool:
    current_time = now or datetime.now(timezone.utc)
    skew = abs(int(current_time.timestamp()) - timestamp)
    if skew > max_skew_seconds:
        raise SecurityError("message timestamp outside allowed skew")

    message = _canonical_message(node_id=node_id, timestamp=timestamp, nonce=nonce, payload=payload)
    try:
        public_key.verify(base64.b64decode(signature.encode("ascii")), message)
    except (InvalidSignature, ValueError) as exc:
        raise SecurityError("invalid message signature") from exc
    return True


def _canonical_message(*, node_id: str, timestamp: int, nonce: str, payload: bytes) -> bytes:
    payload_hash = hashlib.sha256(payload).hexdigest()
    body = {
        "node_id": node_id,
        "nonce": nonce,
        "payload_hash": payload_hash,
        "timestamp": timestamp,
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")