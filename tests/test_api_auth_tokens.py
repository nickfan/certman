from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from certman.api.app import create_app


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_server_client(
    tmp_path: Path,
    *,
    token_auth_enabled: bool = False,
    global_token: str | None = None,
    site_a_token: str | None = None,
    site_b_token: str | None = None,
) -> TestClient:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)

    global_token_line = f'token = "{global_token}"\n' if global_token else ""
    site_a_token_line = f'token = "{site_a_token}"\n' if site_a_token else ""
    site_b_token_line = f'token = "{site_b_token}"\n' if site_b_token else ""
    token_auth_enabled_line = f"token_auth_enabled = {'true' if token_auth_enabled else 'false'}"

    (conf_dir / "config.toml").write_text(
        (
            """
run_mode = "server"

[global]
data_dir = "data"
email = "ops@example.com"
{global_token_line}

[[entries]]
name = "site-a"
primary_domain = "a.example.com"
dns_provider = "aliyun"
{site_a_token_line}

[[entries]]
name = "site-b"
primary_domain = "b.example.com"
dns_provider = "aliyun"
{site_b_token_line}

[server]
db_path = "data/run/certman.db"
listen_host = "127.0.0.1"
listen_port = 8000
{token_auth_enabled_line}
"""
        )
        .strip()
        .format(
            global_token_line=global_token_line,
            site_a_token_line=site_a_token_line,
            site_b_token_line=site_b_token_line,
            token_auth_enabled_line=token_auth_enabled_line,
        ),
        encoding="utf-8",
    )
    return TestClient(create_app(data_dir=str(data_dir), config_file="config.toml"))


def test_no_token_config_keeps_endpoints_open(tmp_path: Path) -> None:
    client = _make_server_client(tmp_path)

    create_resp = client.post("/api/v1/certificates", json={"entry_name": "site-a"})
    assert create_resp.status_code == 202

    get_resp = client.get("/api/v1/certificates/site-a")
    assert get_resp.status_code == 200


def test_global_token_applies_when_item_token_not_set(tmp_path: Path) -> None:
    client = _make_server_client(tmp_path, token_auth_enabled=True, global_token="global-token")

    missing = client.get("/api/v1/certificates/site-a")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "AUTH_MISSING_TOKEN"

    wrong = client.get("/api/v1/certificates/site-a", headers=_auth("wrong-token"))
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "AUTH_INVALID_TOKEN"

    ok = client.get("/api/v1/certificates/site-a", headers=_auth("global-token"))
    assert ok.status_code == 200


def test_item_token_overrides_global_token(tmp_path: Path) -> None:
    client = _make_server_client(
        tmp_path,
        token_auth_enabled=True,
        global_token="global-token",
        site_a_token="item-a-token",
    )

    # site-a must use its own token, global token is rejected.
    site_a_with_global = client.get("/api/v1/certificates/site-a", headers=_auth("global-token"))
    assert site_a_with_global.status_code == 401
    assert site_a_with_global.json()["error"]["code"] == "AUTH_INVALID_TOKEN"

    site_a_with_item = client.get("/api/v1/certificates/site-a", headers=_auth("item-a-token"))
    assert site_a_with_item.status_code == 200

    # site-b falls back to global token.
    site_b_with_global = client.get("/api/v1/certificates/site-b", headers=_auth("global-token"))
    assert site_b_with_global.status_code == 200


def test_issue_and_job_get_follow_item_token_precedence(tmp_path: Path) -> None:
    client = _make_server_client(
        tmp_path,
        token_auth_enabled=True,
        global_token="global-token",
        site_a_token="item-a-token",
    )

    create_missing = client.post("/api/v1/certificates", json={"entry_name": "site-a"})
    assert create_missing.status_code == 401

    create_global = client.post(
        "/api/v1/certificates",
        json={"entry_name": "site-a"},
        headers=_auth("global-token"),
    )
    assert create_global.status_code == 401

    create_item = client.post(
        "/api/v1/certificates",
        json={"entry_name": "site-a"},
        headers=_auth("item-a-token"),
    )
    assert create_item.status_code == 202
    job_id = create_item.json()["data"]["job_id"]

    job_with_global = client.get(f"/api/v1/jobs/{job_id}", headers=_auth("global-token"))
    assert job_with_global.status_code == 401

    job_with_item = client.get(f"/api/v1/jobs/{job_id}", headers=_auth("item-a-token"))
    assert job_with_item.status_code == 200


def test_token_auth_disabled_keeps_routes_open_even_if_tokens_exist(tmp_path: Path) -> None:
    client = _make_server_client(
        tmp_path,
        token_auth_enabled=False,
        global_token="global-token",
        site_a_token="item-a-token",
    )

    response = client.get("/api/v1/certificates/site-a")
    assert response.status_code == 200


def test_token_auth_enabled_without_effective_tokens_returns_config_error(tmp_path: Path) -> None:
    client = _make_server_client(tmp_path, token_auth_enabled=True)

    # item route: no item token and no global token => internal config error
    entry_resp = client.get("/api/v1/certificates/site-a")
    assert entry_resp.status_code == 500
    assert entry_resp.json()["error"]["code"] == "AUTH_TOKEN_CONFIG_ERROR"

    # global route: global token missing => internal config error
    global_resp = client.get("/api/v1/certificates")
    assert global_resp.status_code == 500
    assert global_resp.json()["error"]["code"] == "AUTH_TOKEN_CONFIG_ERROR"
