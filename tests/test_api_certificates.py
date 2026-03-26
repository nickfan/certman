from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from certman.api.app import create_app


def _make_server_client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
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
""".strip(),
        encoding="utf-8",
    )
    return TestClient(create_app(data_dir=str(data_dir), config_file="config.toml"))


def test_post_certificates_returns_202_and_job_id(tmp_path: Path) -> None:
    client = _make_server_client(tmp_path)

    response = client.post("/api/v1/certificates", json={"entry_name": "site-a"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["job_id"]


def test_get_job_returns_enveloped_job(tmp_path: Path) -> None:
    client = _make_server_client(tmp_path)
    create_response = client.post("/api/v1/certificates", json={"entry_name": "site-a"})
    job_id = create_response.json()["data"]["job_id"]

    response = client.get(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["job_id"] == job_id
    assert payload["data"]["status"] == "queued"


def test_post_certificates_rejects_unknown_entry(tmp_path: Path) -> None:
    client = _make_server_client(tmp_path)

    response = client.post("/api/v1/certificates", json={"entry_name": "missing-site"})

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "NOT_FOUND_ENTRY"
