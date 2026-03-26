from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient

from certman.api.app import create_app
from certman.config import create_runtime, resolve_runtime_path
from certman.db.engine import make_session_factory
from certman.db.models import NodeORM
from certman.security.identity import (
    generate_ed25519_keypair,
    load_ed25519_private_key,
)
from certman.security.signing import sign_message
from certman.services.job_service import JobService


def _prepare_server_with_node(tmp_path: Path) -> tuple[TestClient, Path, Path]:
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
                status="active",
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