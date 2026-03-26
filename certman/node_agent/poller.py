from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from certman.security.identity import load_ed25519_private_key
from certman.security.signing import sign_message


class NodePoller:
    def __init__(self, *, endpoint: str, node_id: str, private_key_path: str | Path | None = None):
        self._endpoint = endpoint
        self._node_id = node_id
        self._private_key_path = Path(private_key_path) if private_key_path else None

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def node_id(self) -> str:
        return self._node_id

    def poll(self) -> list[dict]:
        if self._private_key_path is None or not self._private_key_path.exists():
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
