from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from certman.api.app import create_app


def _make_server_client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    key_dir = data_dir / "run" / "keys"
    conf_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)
    private_key = Ed25519PrivateKey.generate()
    (key_dir / "server_ed25519.pem").write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (conf_dir / "config.toml").write_text(
        """
run_mode = "server"

[global]
data_dir = "data"
email = "ops@example.com"

[[entries]]
name = "site-a"
primary_domain = "example.com"
dns_provider = "aliyun"

[server]
db_path = "data/run/certman.db"
listen_host = "127.0.0.1"
listen_port = 8000
signing_key_path = "data/run/keys/server_ed25519.pem"
""".strip(),
        encoding="utf-8",
    )
    return TestClient(create_app(data_dir=str(data_dir), config_file="config.toml"))


def test_openapi_documentation_endpoints_are_exposed(tmp_path: Path) -> None:
    client = _make_server_client(tmp_path)

    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_openapi_schema_contains_key_control_plane_paths(tmp_path: Path) -> None:
    client = _make_server_client(tmp_path)

    payload = client.get("/openapi.json").json()

    assert payload["info"]["title"] == "CertMan Control Plane"
    assert "/api/v1/certificates" in payload["paths"]
    assert "/api/v1/jobs" in payload["paths"]
    assert "/api/v1/webhooks" in payload["paths"]
    assert "/api/v1/nodes/register" in payload["paths"]
    assert "/api/v1/node-agent/poll" in payload["paths"]