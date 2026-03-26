from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from certman.api.app import create_app


def test_health_endpoint_returns_ok(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
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
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(create_app(data_dir=str(data_dir), config_file="config.toml"))
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
