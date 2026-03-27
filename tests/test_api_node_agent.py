from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

from fastapi.testclient import TestClient

from certman.api.app import create_app
from certman.config import create_runtime, resolve_runtime_path
from certman.db.engine import make_session_factory
from certman.db.models import NodeORM
from certman.security.envelope import Envelope, decrypt_envelope
from certman.security.identity import (
    generate_ed25519_keypair,
    generate_x25519_keypair,
    load_ed25519_private_key,
    load_x25519_private_key,
)
from certman.security.signing import sign_message
from certman.services.job_service import JobService


def _prepare_server_with_node(tmp_path: Path, *, node_status: str = "active") -> tuple[TestClient, Path, Path]:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    key_dir = data_dir / "run" / "keys"
    conf_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)

    node_private = key_dir / "node-a.pem"
    node_public = key_dir / "node-a.pub.pem"
    server_private = key_dir / "server.pem"
    server_public = key_dir / "server.pub.pem"
    generate_ed25519_keypair(node_private, node_public)
    generate_ed25519_keypair(server_private, server_public)

    (conf_dir / "config.toml").write_text(
        """
run_mode = "server"

[global]
data_dir = "data"
email = "ops@example.com"

[server]
db_path = "data/run/certman.db"
listen_host = "127.0.0.1"
listen_port = 8000
signing_key_path = "data/run/keys/server.pem"
bundle_token_required = false

[[entries]]
name = "site-a"
primary_domain = "site-a.example.com"
dns_provider = "route53"
""".strip(),
        encoding="utf-8",
    )

    runtime = create_runtime(data_dir=str(data_dir), config_file="config.toml")
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    JobService(db_path=db_path)
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        session.add(
            NodeORM(
                node_id="node-a",
                node_type="agent",
                public_key=node_public.read_text(encoding="utf-8"),
                status=node_status,
            )
        )
        session.commit()

    client = TestClient(create_app(data_dir=str(data_dir), config_file="config.toml"))
    return client, node_private, db_path


def test_node_agent_poll_requires_valid_signature_and_blocks_replay(tmp_path: Path) -> None:
    client, node_private_path, _ = _prepare_server_with_node(tmp_path)
    private_key = load_ed25519_private_key(node_private_path)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    signature = sign_message(
        private_key,
        node_id="node-a",
        timestamp=timestamp,
        nonce="nonce-1",
        payload=b"",
    )
    payload = {
        "node_id": "node-a",
        "timestamp": timestamp,
        "nonce": "nonce-1",
        "agent_version": "0.1.0",
        "signature": signature,
    }

    first = client.post("/api/v1/node-agent/poll", json=payload)
    second = client.post("/api/v1/node-agent/poll", json=payload)

    assert first.status_code == 200
    assert first.json()["success"] is True
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT_REPLAY"


def test_node_agent_result_updates_job_status_with_signature(tmp_path: Path) -> None:
    client, node_private_path, db_path = _prepare_server_with_node(tmp_path)
    job_service = JobService(db_path=db_path)
    job = job_service.create_job(job_type="issue", subject_id="site-a", node_id="node-a")
    job_service.update_status(job.job_id, status="running")
    private_key = load_ed25519_private_key(node_private_path)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    output = "ok"
    signed_payload = json.dumps(
        {
            "job_id": job.job_id,
            "status": "completed",
            "output": output,
            "error": None,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = sign_message(
        private_key,
        node_id="node-a",
        timestamp=timestamp,
        nonce="nonce-r1",
        payload=signed_payload,
    )

    response = client.post(
        "/api/v1/node-agent/result",
        json={
            "node_id": "node-a",
            "job_id": job.job_id,
            "status": "completed",
            "output": output,
            "error": None,
            "timestamp": timestamp,
            "nonce": "nonce-r1",
            "signature": signature,
        },
    )

    updated = job_service.get_job(job.job_id)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert updated is not None
    assert updated.status == "completed"
    assert updated.result == "ok"


def test_node_agent_poll_rejects_disabled_node(tmp_path: Path) -> None:
    client, _, _ = _prepare_server_with_node(tmp_path, node_status="disabled")
    response = client.post(
        "/api/v1/node-agent/poll",
        json={
            "node_id": "node-a",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "nonce": "nonce-disabled",
            "agent_version": "0.1.0",
            "signature": "invalid",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_NODE_DISABLED"


def test_node_agent_poll_updates_last_seen(tmp_path: Path) -> None:
    client, node_private_path, db_path = _prepare_server_with_node(tmp_path)
    private_key = load_ed25519_private_key(node_private_path)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    signature = sign_message(
        private_key,
        node_id="node-a",
        timestamp=timestamp,
        nonce="nonce-last-seen",
        payload=b"",
    )

    response = client.post(
        "/api/v1/node-agent/poll",
        json={
            "node_id": "node-a",
            "timestamp": timestamp,
            "nonce": "nonce-last-seen",
            "agent_version": "0.1.0",
            "signature": signature,
        },
    )

    assert response.status_code == 200

    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        node = session.query(NodeORM).filter(NodeORM.node_id == "node-a").first()
        assert node is not None
        assert node.last_seen is not None


def test_node_agent_poll_rejects_pending_node(tmp_path: Path) -> None:
    client, _, _ = _prepare_server_with_node(tmp_path, node_status="pending")
    response = client.post(
        "/api/v1/node-agent/poll",
        json={
            "node_id": "node-a",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "nonce": "nonce-pending",
            "agent_version": "0.1.0",
            "signature": "invalid",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_NODE_NOT_APPROVED"


def test_node_agent_poll_throttles_last_seen_updates(tmp_path: Path) -> None:
    """Test that last_seen updates are throttled to 45s window to reduce write pressure."""
    from datetime import timedelta
    
    client, node_private, db_path = _prepare_server_with_node(tmp_path)
    
    # First poll: last_seen_updated_at should be set
    ts1 = int(datetime.now(timezone.utc).timestamp())
    sig1 = sign_message(
        load_ed25519_private_key(node_private),
        node_id="node-a",
        timestamp=ts1,
        nonce="nonce-throttle-1",
        payload=b"",
    )
    response1 = client.post(
        "/api/v1/node-agent/poll",
        json={
            "node_id": "node-a",
            "timestamp": ts1,
            "nonce": "nonce-throttle-1",
            "agent_version": "0.1.0",
            "signature": sig1,
        },
    )
    assert response1.status_code == 200
    
    # Check first update was recorded
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        node = session.query(NodeORM).filter(NodeORM.node_id == "node-a").first()
        first_last_seen = node.last_seen
        first_updated_at = node.last_seen_updated_at
        assert first_last_seen is not None
        assert first_updated_at is not None
    
    # Second poll within throttle window (10s later): should NOT update last_seen_updated_at
    ts2 = int(datetime.now(timezone.utc).timestamp())
    sig2 = sign_message(
        load_ed25519_private_key(node_private),
        node_id="node-a",
        timestamp=ts2,
        nonce="nonce-throttle-2",
        payload=b"",
    )
    response2 = client.post(
        "/api/v1/node-agent/poll",
        json={
            "node_id": "node-a",
            "timestamp": ts2,
            "nonce": "nonce-throttle-2",
            "agent_version": "0.1.0",
            "signature": sig2,
        },
    )
    assert response2.status_code == 200
    
    # Verify update was throttled (last_seen_updated_at unchanged)
    with session_factory() as session:
        node = session.query(NodeORM).filter(NodeORM.node_id == "node-a").first()
        assert node.last_seen_updated_at == first_updated_at
    
    # Third poll outside throttle window: backdate last_seen_updated_at by 60s
    with session_factory() as session:
        node = session.query(NodeORM).filter(NodeORM.node_id == "node-a").first()
        backdated = node.last_seen_updated_at - timedelta(seconds=60)
        node.last_seen_updated_at = backdated
        session.commit()

    ts3 = int(datetime.now(timezone.utc).timestamp())
    sig3 = sign_message(
        load_ed25519_private_key(node_private),
        node_id="node-a",
        timestamp=ts3,
        nonce="nonce-throttle-3",
        payload=b"",
    )
    response3 = client.post(
        "/api/v1/node-agent/poll",
        json={
            "node_id": "node-a",
            "timestamp": ts3,
            "nonce": "nonce-throttle-3",
            "agent_version": "0.1.0",
            "signature": sig3,
        },
    )
    assert response3.status_code == 200

    # Verify update occurred after throttle window
    with session_factory() as session:
        node = session.query(NodeORM).filter(NodeORM.node_id == "node-a").first()
        assert node.last_seen_updated_at > first_updated_at


def test_node_agent_subscribe_long_poll_delivers_assignment(tmp_path: Path) -> None:
    client, node_private_path, db_path = _prepare_server_with_node(tmp_path)
    private_key = load_ed25519_private_key(node_private_path)
    job_service = JobService(db_path=db_path)
    job_service.create_job(job_type="renew", subject_id="site-a", node_id="node-a")

    timestamp = int(datetime.now(timezone.utc).timestamp())
    signature = sign_message(
        private_key,
        node_id="node-a",
        timestamp=timestamp,
        nonce="nonce-subscribe-1",
        payload=b"",
    )

    response = client.post(
        "/api/v1/node-agent/subscribe?wait_seconds=1",
        json={
            "node_id": "node-a",
            "timestamp": timestamp,
            "nonce": "nonce-subscribe-1",
            "agent_version": "0.1.0",
            "signature": signature,
        },
    )

    assert response.status_code == 200
    assignments = response.json()["data"]["assignments"]
    assert len(assignments) == 1
    assert assignments[0]["job_type"] == "renew"
    assert assignments[0]["bundle_token"] is not None


def test_node_agent_bundle_download_encrypted(tmp_path: Path) -> None:
    """Bundle returned as ECIES envelope when server bundle_encryption=encrypt and node has X25519 key."""
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    key_dir = data_dir / "run" / "keys"
    conf_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)

    node_private = key_dir / "node-a.pem"
    node_public = key_dir / "node-a.pub.pem"
    node_enc_private = key_dir / "node-a-enc.pem"
    node_enc_public = key_dir / "node-a-enc.pub.pem"
    server_private = key_dir / "server.pem"
    server_public = key_dir / "server.pub.pem"
    generate_ed25519_keypair(node_private, node_public)
    generate_x25519_keypair(node_enc_private, node_enc_public)
    generate_ed25519_keypair(server_private, server_public)

    (conf_dir / "config.toml").write_text(
        """
run_mode = "server"

[global]
data_dir = "data"
email = "ops@example.com"

[server]
db_path = "data/run/certman.db"
listen_host = "127.0.0.1"
listen_port = 8000
signing_key_path = "data/run/keys/server.pem"
bundle_encryption = "encrypt"
bundle_token_required = false

[[entries]]
name = "site-a"
primary_domain = "site-a.example.com"
dns_provider = "route53"
""".strip(),
        encoding="utf-8",
    )

    runtime = create_runtime(data_dir=str(data_dir), config_file="config.toml")
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    job_service = JobService(db_path=db_path)

    # Seed cert files
    live_dir = runtime.paths.run_dir / "letsencrypt" / "live" / "site-a.example.com"
    live_dir.mkdir(parents=True)
    (live_dir / "fullchain.pem").write_text("FULLCHAIN", encoding="utf-8")
    (live_dir / "privkey.pem").write_text("PRIVKEY", encoding="utf-8")

    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        session.add(
            NodeORM(
                node_id="node-a",
                node_type="agent",
                public_key=node_public.read_text(encoding="utf-8"),
                encryption_public_key=node_enc_public.read_text(encoding="utf-8"),
                status="active",
            )
        )
        session.commit()

    created_job = job_service.create_job(job_type="issue", subject_id="site-a", node_id="node-a")
    job_service.update_status(created_job.job_id, status="running")

    client = TestClient(create_app(data_dir=str(data_dir), config_file="config.toml"))

    private_key = load_ed25519_private_key(node_private)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    payload_bytes = json.dumps({"job_id": created_job.job_id}, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = sign_message(
        private_key,
        node_id="node-a",
        timestamp=timestamp,
        nonce="nonce-enc-bundle",
        payload=payload_bytes,
    )

    response = client.get(
        f"/api/v1/node-agent/bundles/{created_job.job_id}",
        params={
            "node_id": "node-a",
            "timestamp": timestamp,
            "nonce": "nonce-enc-bundle",
            "signature": signature,
        },
    )
    if response.status_code == 401 and response.json().get("error", {}).get("code") == "AUTH_BUNDLE_TOKEN_REQUIRED":
        poll_ts = int(datetime.now(timezone.utc).timestamp())
        poll_sig = sign_message(
            private_key,
            node_id="node-a",
            timestamp=poll_ts,
            nonce="nonce-enc-poll",
            payload=b"",
        )
        poll_resp = client.post(
            "/api/v1/node-agent/poll",
            json={
                "node_id": "node-a",
                "timestamp": poll_ts,
                "nonce": "nonce-enc-poll",
                "agent_version": "0.1.0",
                "signature": poll_sig,
            },
        )
        assert poll_resp.status_code == 200
        token = poll_resp.json()["data"]["assignments"][0]["bundle_token"]

        timestamp = int(datetime.now(timezone.utc).timestamp())
        signature = sign_message(
            private_key,
            node_id="node-a",
            timestamp=timestamp,
            nonce="nonce-enc-bundle-token",
            payload=payload_bytes,
        )
        response = client.get(
            f"/api/v1/node-agent/bundles/{created_job.job_id}",
            params={
                "node_id": "node-a",
                "timestamp": timestamp,
                "nonce": "nonce-enc-bundle-token",
                "signature": signature,
                "bundle_token": token,
            },
        )
    assert response.status_code == 200
    data = response.json()["data"]

    # Plaintext bundle should be absent
    assert data["bundle"] is None
    # Envelope must be present
    assert data["envelope"] is not None
    assert "ephemeral_public_key" in data["envelope"]
    assert "nonce" in data["envelope"]
    assert "ciphertext" in data["envelope"]

    # Decrypt with node's X25519 private key
    enc_priv = load_x25519_private_key(node_enc_private)
    envelope = Envelope(
        ephemeral_public_key=data["envelope"]["ephemeral_public_key"],
        nonce=data["envelope"]["nonce"],
        ciphertext=data["envelope"]["ciphertext"],
    )
    plaintext = decrypt_envelope(enc_priv, envelope)
    if data.get("compressed", False):
        plaintext = gzip.decompress(plaintext)
    inner = json.loads(plaintext.decode("utf-8"))
    assert inner["bundle"]["files"]["fullchain.pem"] == "FULLCHAIN"
    assert inner["bundle"]["files"]["privkey.pem"] == "PRIVKEY"

def test_node_agent_bundle_download_with_signature(tmp_path: Path) -> None:
    client, node_private_path, db_path = _prepare_server_with_node(tmp_path)
    private_key = load_ed25519_private_key(node_private_path)

    data_dir = tmp_path / "data"
    live_dir = data_dir / "run" / "letsencrypt" / "live" / "site-a.example.com"
    live_dir.mkdir(parents=True)
    (live_dir / "fullchain.pem").write_text("fullchain-data", encoding="utf-8")
    (live_dir / "privkey.pem").write_text("privkey-data", encoding="utf-8")
    (live_dir / "cert.pem").write_text("cert-data", encoding="utf-8")
    (live_dir / "chain.pem").write_text("chain-data", encoding="utf-8")

    job_service = JobService(db_path=db_path)
    job = job_service.create_job(job_type="renew", subject_id="site-a", node_id="node-a")
    job_service.update_status(job.job_id, status="running")

    timestamp = int(datetime.now(timezone.utc).timestamp())
    payload_bytes = json.dumps({"job_id": job.job_id}, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = sign_message(
        private_key,
        node_id="node-a",
        timestamp=timestamp,
        nonce="nonce-bundle-1",
        payload=payload_bytes,
    )

    response = client.get(
        f"/api/v1/node-agent/bundles/{job.job_id}",
        params={
            "node_id": "node-a",
            "timestamp": timestamp,
            "nonce": "nonce-bundle-1",
            "signature": signature,
        },
    )
    if response.status_code == 401 and response.json().get("error", {}).get("code") == "AUTH_BUNDLE_TOKEN_REQUIRED":
        poll_ts = int(datetime.now(timezone.utc).timestamp())
        poll_sig = sign_message(
            private_key,
            node_id="node-a",
            timestamp=poll_ts,
            nonce="nonce-bundle-poll-1",
            payload=b"",
        )
        poll_resp = client.post(
            "/api/v1/node-agent/poll",
            json={
                "node_id": "node-a",
                "timestamp": poll_ts,
                "nonce": "nonce-bundle-poll-1",
                "agent_version": "0.1.0",
                "signature": poll_sig,
            },
        )
        assert poll_resp.status_code == 200
        token = poll_resp.json()["data"]["assignments"][0]["bundle_token"]

        ts2 = int(datetime.now(timezone.utc).timestamp())
        sig2 = sign_message(
            private_key,
            node_id="node-a",
            timestamp=ts2,
            nonce="nonce-bundle-2",
            payload=payload_bytes,
        )
        response = client.get(
            f"/api/v1/node-agent/bundles/{job.job_id}",
            params={
                "node_id": "node-a",
                "timestamp": ts2,
                "nonce": "nonce-bundle-2",
                "signature": sig2,
                "bundle_token": token,
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["job_id"] == job.job_id
    assert data["bundle"]["entry_name"] == "site-a"
    assert data["bundle"]["files"]["fullchain.pem"] == "fullchain-data"
    assert data["bundle"]["files"]["privkey.pem"] == "privkey-data"


def test_node_agent_bundle_download_requires_token_when_enabled(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    key_dir = data_dir / "run" / "keys"
    conf_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)

    node_private = key_dir / "node-a.pem"
    node_public = key_dir / "node-a.pub.pem"
    server_private = key_dir / "server.pem"
    server_public = key_dir / "server.pub.pem"
    generate_ed25519_keypair(node_private, node_public)
    generate_ed25519_keypair(server_private, server_public)

    (conf_dir / "config.toml").write_text(
        """
run_mode = "server"

[global]
data_dir = "data"
email = "ops@example.com"

[server]
db_path = "data/run/certman.db"
listen_host = "127.0.0.1"
listen_port = 8000
signing_key_path = "data/run/keys/server.pem"
bundle_token_required = true

[[entries]]
name = "site-a"
primary_domain = "site-a.example.com"
dns_provider = "route53"
""".strip(),
        encoding="utf-8",
    )

    runtime = create_runtime(data_dir=str(data_dir), config_file="config.toml")
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    job_service = JobService(db_path=db_path)
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        session.add(
            NodeORM(
                node_id="node-a",
                node_type="agent",
                public_key=node_public.read_text(encoding="utf-8"),
                status="active",
            )
        )
        session.commit()

    live_dir = runtime.paths.run_dir / "letsencrypt" / "live" / "site-a.example.com"
    live_dir.mkdir(parents=True)
    (live_dir / "fullchain.pem").write_text("fullchain-data", encoding="utf-8")
    (live_dir / "privkey.pem").write_text("privkey-data", encoding="utf-8")

    job = job_service.create_job(job_type="renew", subject_id="site-a", node_id="node-a")

    client = TestClient(create_app(data_dir=str(data_dir), config_file="config.toml"))
    private_key = load_ed25519_private_key(node_private)

    # Poll once to claim job and obtain short-lived bundle token.
    poll_ts = int(datetime.now(timezone.utc).timestamp())
    poll_sig = sign_message(private_key, node_id="node-a", timestamp=poll_ts, nonce="nonce-poll-token", payload=b"")
    poll_resp = client.post(
        "/api/v1/node-agent/poll",
        json={
            "node_id": "node-a",
            "timestamp": poll_ts,
            "nonce": "nonce-poll-token",
            "agent_version": "0.1.0",
            "signature": poll_sig,
        },
    )
    assert poll_resp.status_code == 200
    assignment = poll_resp.json()["data"]["assignments"][0]
    token = assignment["bundle_token"]
    assert token

    # Missing token should be rejected.
    ts_missing = int(datetime.now(timezone.utc).timestamp())
    sig_missing = sign_message(
        private_key,
        node_id="node-a",
        timestamp=ts_missing,
        nonce="nonce-bundle-missing-token",
        payload=json.dumps({"job_id": job.job_id}, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )
    missing_resp = client.get(
        f"/api/v1/node-agent/bundles/{job.job_id}",
        params={
            "node_id": "node-a",
            "timestamp": ts_missing,
            "nonce": "nonce-bundle-missing-token",
            "signature": sig_missing,
        },
    )
    assert missing_resp.status_code == 401
    assert missing_resp.json()["error"]["code"] == "AUTH_BUNDLE_TOKEN_REQUIRED"

    # Valid token should pass.
    ts_ok = int(datetime.now(timezone.utc).timestamp())
    sig_ok = sign_message(
        private_key,
        node_id="node-a",
        timestamp=ts_ok,
        nonce="nonce-bundle-with-token",
        payload=json.dumps({"job_id": job.job_id}, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )
    ok_resp = client.get(
        f"/api/v1/node-agent/bundles/{job.job_id}",
        params={
            "node_id": "node-a",
            "timestamp": ts_ok,
            "nonce": "nonce-bundle-with-token",
            "signature": sig_ok,
            "bundle_token": token,
        },
    )
    assert ok_resp.status_code == 200


def test_node_agent_heartbeat_endpoint_updates_liveness(tmp_path: Path) -> None:
    client, node_private_path, _ = _prepare_server_with_node(tmp_path)
    private_key = load_ed25519_private_key(node_private_path)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    signature = sign_message(
        private_key,
        node_id="node-a",
        timestamp=timestamp,
        nonce="nonce-heartbeat-1",
        payload=b"",
    )

    response = client.post(
        "/api/v1/node-agent/heartbeat",
        json={
            "node_id": "node-a",
            "timestamp": timestamp,
            "nonce": "nonce-heartbeat-1",
            "agent_version": "0.1.0",
            "signature": signature,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["assignments"] == []


def test_node_agent_callback_alias_updates_job_status(tmp_path: Path) -> None:
    client, node_private_path, db_path = _prepare_server_with_node(tmp_path)
    job_service = JobService(db_path=db_path)
    job = job_service.create_job(job_type="issue", subject_id="site-a", node_id="node-a")
    job_service.update_status(job.job_id, status="running")
    private_key = load_ed25519_private_key(node_private_path)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    output = "ok-callback"
    signed_payload = json.dumps(
        {
            "job_id": job.job_id,
            "status": "completed",
            "output": output,
            "error": None,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = sign_message(
        private_key,
        node_id="node-a",
        timestamp=timestamp,
        nonce="nonce-callback-1",
        payload=signed_payload,
    )

    response = client.post(
        "/api/v1/node-agent/callback",
        json={
            "node_id": "node-a",
            "job_id": job.job_id,
            "status": "completed",
            "output": output,
            "error": None,
            "timestamp": timestamp,
            "nonce": "nonce-callback-1",
            "signature": signature,
        },
    )

    updated = job_service.get_job(job.job_id)
    assert response.status_code == 200
    assert updated is not None
    assert updated.status == "completed"
    assert updated.result == "ok-callback"