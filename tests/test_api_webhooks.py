from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from certman.api.app import create_app


def test_create_webhook_subscription_returns_201(tmp_path: Path) -> None:
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
    response = client.post(
        "/api/v1/webhooks",
        json={"topic": "job.completed", "endpoint": "https://example.test/hook", "secret": "topsecret"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["id"]