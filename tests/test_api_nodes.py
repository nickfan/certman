from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from certman.api.app import create_app
from certman.config import create_runtime, resolve_runtime_path
from certman.db.engine import make_session_factory
from certman.db.models import NodeORM
from certman.security.identity import generate_ed25519_keypair
from certman.security.identity import generate_x25519_keypair


def _prepare_server(tmp_path: Path, monkeypatch, token: str | None = "reg-token") -> tuple[TestClient, Path]:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    key_dir = data_dir / "run" / "keys"
    conf_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)

    server_private = key_dir / "server.pem"
    server_public = key_dir / "server.pub.pem"
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

    if token is not None:
        monkeypatch.setenv("CERTMAN_NODE_REGISTRATION_TOKEN", token)
    else:
        monkeypatch.delenv("CERTMAN_NODE_REGISTRATION_TOKEN", raising=False)

    client = TestClient(create_app(data_dir=str(data_dir), config_file="config.toml"))
    return client, data_dir


def _new_public_key(tmp_path: Path, name: str) -> str:
    private_key = tmp_path / f"{name}.pem"
    public_key = tmp_path / f"{name}.pub.pem"
    generate_ed25519_keypair(private_key, public_key)
    return public_key.read_text(encoding="utf-8")


def test_nodes_register_requires_configured_token(tmp_path: Path, monkeypatch) -> None:
    client, _ = _prepare_server(tmp_path, monkeypatch, token=None)
    public_key = _new_public_key(tmp_path, "node-a")

    response = client.post(
        "/api/v1/nodes/register",
        json={
            "node_id": "node-a",
            "node_type": "agent",
            "public_key": public_key,
            "register_token": "x",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "REGISTER_TOKEN_NOT_CONFIGURED"


def test_nodes_register_rejects_invalid_token(tmp_path: Path, monkeypatch) -> None:
    client, _ = _prepare_server(tmp_path, monkeypatch, token="expected-token")
    public_key = _new_public_key(tmp_path, "node-a")

    response = client.post(
        "/api/v1/nodes/register",
        json={
            "node_id": "node-a",
            "node_type": "agent",
            "public_key": public_key,
            "register_token": "wrong-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_REGISTRATION_TOKEN"


def test_nodes_register_success_and_idempotent(tmp_path: Path, monkeypatch) -> None:
    client, data_dir = _prepare_server(tmp_path, monkeypatch, token="reg-token")
    public_key = _new_public_key(tmp_path, "node-a")

    first = client.post(
        "/api/v1/nodes/register",
        json={
            "node_id": "node-a",
            "node_type": "agent",
            "public_key": public_key,
            "register_token": "reg-token",
        },
    )
    second = client.post(
        "/api/v1/nodes/register",
        json={
            "node_id": "node-a",
            "node_type": "agent",
            "public_key": public_key,
            "register_token": "reg-token",
        },
    )

    assert first.status_code == 201
    assert first.json()["data"]["created"] is True
    assert second.status_code == 200
    assert second.json()["data"]["created"] is False

    runtime = create_runtime(data_dir=str(data_dir), config_file="config.toml")
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        nodes = session.query(NodeORM).all()
        assert len(nodes) == 1
        assert nodes[0].node_id == "node-a"
        assert (nodes[0].public_key or "").strip() == public_key.strip()


def test_nodes_register_conflict_with_different_key(tmp_path: Path, monkeypatch) -> None:
    client, _ = _prepare_server(tmp_path, monkeypatch, token="reg-token")
    key_a = _new_public_key(tmp_path, "node-a")
    key_b = _new_public_key(tmp_path, "node-b")

    first = client.post(
        "/api/v1/nodes/register",
        json={
            "node_id": "node-a",
            "node_type": "agent",
            "public_key": key_a,
            "register_token": "reg-token",
        },
    )
    second = client.post(
        "/api/v1/nodes/register",
        json={
            "node_id": "node-a",
            "node_type": "agent",
            "public_key": key_b,
            "register_token": "reg-token",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT_NODE_ALREADY_REGISTERED"


def test_nodes_register_rejects_invalid_public_key(tmp_path: Path, monkeypatch) -> None:
    client, _ = _prepare_server(tmp_path, monkeypatch, token="reg-token")

    response = client.post(
        "/api/v1/nodes/register",
        json={
            "node_id": "node-a",
            "node_type": "agent",
            "public_key": "not-a-pem",
            "register_token": "reg-token",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PUBLIC_KEY"


def test_nodes_register_rejects_non_ed25519_key(tmp_path: Path, monkeypatch) -> None:
    client, _ = _prepare_server(tmp_path, monkeypatch, token="reg-token")
    private_key = tmp_path / "x25519.pem"
    public_key = tmp_path / "x25519.pub.pem"
    generate_x25519_keypair(private_key, public_key)

    response = client.post(
        "/api/v1/nodes/register",
        json={
            "node_id": "node-a",
            "node_type": "agent",
            "public_key": public_key.read_text(encoding="utf-8"),
            "register_token": "reg-token",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PUBLIC_KEY_ALGORITHM"
