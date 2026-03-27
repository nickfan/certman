from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from certman.api.app import create_app


def _make_client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.toml").write_text(
        """
run_mode = "server"

[global]
data_dir = "data"
email = "ops@example.com"
scan_items_glob = "item_*.toml"

[server]
db_path = "data/run/certman.db"
listen_host = "127.0.0.1"
listen_port = 8000
""".strip(),
        encoding="utf-8",
    )
    (conf_dir / "item_site-a.toml").write_text(
        """
primary_domain = "example.com"
dns_provider = "aliyun"
account_id = "test-account"
""".strip(),
        encoding="utf-8",
    )
    return TestClient(create_app(data_dir=str(data_dir), config_file="config.toml"))


def test_config_entries_list_and_show(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    list_resp = client.get("/api/v1/config/entries")
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert list_payload["success"] is True
    assert list_payload["data"][0]["name"] == "site-a"

    show_resp = client.get("/api/v1/config/entries/site-a")
    assert show_resp.status_code == 200
    show_payload = show_resp.json()
    assert show_payload["success"] is True
    assert show_payload["data"]["primary_domain"] == "example.com"


def test_config_show_returns_404_for_missing_entry(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    response = client.get("/api/v1/config/entries/missing")

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "NOT_FOUND_ENTRY"


def test_config_validate_requires_scope(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    response = client.post("/api/v1/config/validate", json={"entry_names": [], "validate_all": False})

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_CONFIG"
