from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from certman.security.identity import generate_ed25519_keypair, load_ed25519_private_key, load_ed25519_public_key
from certman.security.signing import SecurityError, sign_message, verify_message


def test_sign_and_verify_message(tmp_path) -> None:
    private_key_path = tmp_path / "node.pem"
    public_key_path = tmp_path / "node.pub.pem"
    generate_ed25519_keypair(private_key_path, public_key_path)

    private_key = load_ed25519_private_key(private_key_path)
    public_key = load_ed25519_public_key(public_key_path)
    payload = b'{"job_id":"job-1"}'

    signature = sign_message(
        private_key,
        node_id="node-a",
        timestamp=int(datetime.now(timezone.utc).timestamp()),
        nonce="nonce-1",
        payload=payload,
    )

    assert verify_message(
        public_key,
        signature,
        node_id="node-a",
        timestamp=int(datetime.now(timezone.utc).timestamp()),
        nonce="nonce-1",
        payload=payload,
    ) is True


def test_verify_message_rejects_tampered_payload(tmp_path) -> None:
    private_key_path = tmp_path / "node.pem"
    public_key_path = tmp_path / "node.pub.pem"
    generate_ed25519_keypair(private_key_path, public_key_path)

    private_key = load_ed25519_private_key(private_key_path)
    public_key = load_ed25519_public_key(public_key_path)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    signature = sign_message(private_key, node_id="node-a", timestamp=timestamp, nonce="nonce-1", payload=b"ok")

    with pytest.raises(SecurityError):
        verify_message(public_key, signature, node_id="node-a", timestamp=timestamp, nonce="nonce-1", payload=b"tampered")


def test_verify_message_rejects_expired_timestamp(tmp_path) -> None:
    private_key_path = tmp_path / "node.pem"
    public_key_path = tmp_path / "node.pub.pem"
    generate_ed25519_keypair(private_key_path, public_key_path)

    private_key = load_ed25519_private_key(private_key_path)
    public_key = load_ed25519_public_key(public_key_path)
    old_ts = int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())
    signature = sign_message(private_key, node_id="node-a", timestamp=old_ts, nonce="nonce-1", payload=b"ok")

    with pytest.raises(SecurityError):
        verify_message(
            public_key,
            signature,
            node_id="node-a",
            timestamp=old_ts,
            nonce="nonce-1",
            payload=b"ok",
            now=datetime.now(timezone.utc),
            max_skew_seconds=60,
        )