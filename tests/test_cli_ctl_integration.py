"""Integration tests for certmanctl CLI against a real FastAPI ASGI app.

The strategy:
- Build a FastAPI app via create_app() with a temp config
- Monkeypatch httpx.request (used by _call_api) with a TestClient-backed
  function that converts requests.Response → httpx.Response so the real
  ASGI stack is exercised in-process without a network
- Invoke CLI commands via typer.testing.CliRunner and assert stdout / exit codes
"""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import certman.ctl.cli as ctl_module
from certman.api.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = "http://127.0.0.1:8000"


def _make_server_app(tmp_path: Path):
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
    return create_app(data_dir=str(data_dir), config_file="config.toml")


def _patch_httpx(monkeypatch, asgi_app) -> None:
    """Redirect httpx.request → in-process TestClient (no network)."""
    tc = TestClient(asgi_app, raise_server_exceptions=False)

    def _fake_request(method: str, url: str, **kwargs) -> httpx.Response:
        path = url.removeprefix(_BASE)
        kwargs.pop("timeout", None)  # TestClient has its own timeout handling
        json_payload = kwargs.pop("json", None)
        headers = kwargs.pop("headers", {})

        resp = tc.request(method, path, json=json_payload, headers=headers)

        # Convert requests.Response → httpx.Response so _call_api can call
        # .json() and .status_code on the returned object identically
        return httpx.Response(
            status_code=resp.status_code,
            content=resp.content,
            headers=dict(resp.headers),
        )

    monkeypatch.setattr(ctl_module.httpx, "request", _fake_request)


runner = CliRunner()


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

def test_integration_health(monkeypatch, tmp_path: Path) -> None:
    _patch_httpx(monkeypatch, _make_server_app(tmp_path))
    result = runner.invoke(ctl_module.app, ["health"])
    assert result.exit_code == 0
    assert "ok" in result.output.lower()


# ---------------------------------------------------------------------------
# cert create
# ---------------------------------------------------------------------------

def test_integration_cert_create_returns_job_id(monkeypatch, tmp_path: Path) -> None:
    _patch_httpx(monkeypatch, _make_server_app(tmp_path))
    result = runner.invoke(ctl_module.app, ["cert", "create", "--entry-name", "site-a"])
    assert result.exit_code == 0
    assert "job_id" in result.output


def test_integration_cert_create_unknown_entry_exits_api_error(monkeypatch, tmp_path: Path) -> None:
    _patch_httpx(monkeypatch, _make_server_app(tmp_path))
    result = runner.invoke(ctl_module.app, ["cert", "create", "--entry-name", "no-such"])
    assert result.exit_code == ctl_module.EXIT_API_ERROR


# ---------------------------------------------------------------------------
# cert list
# ---------------------------------------------------------------------------

def test_integration_cert_list_empty(monkeypatch, tmp_path: Path) -> None:
    _patch_httpx(monkeypatch, _make_server_app(tmp_path))
    result = runner.invoke(ctl_module.app, ["cert", "list"])
    assert result.exit_code == 0


def test_integration_cert_list_after_create(monkeypatch, tmp_path: Path) -> None:
    app = _make_server_app(tmp_path)
    _patch_httpx(monkeypatch, app)
    runner.invoke(ctl_module.app, ["cert", "create", "--entry-name", "site-a"])

    result = runner.invoke(ctl_module.app, ["--output", "json", "cert", "list"])
    assert result.exit_code == 0
    import json
    items = json.loads(result.output)
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["subject_id"] == "site-a"


# ---------------------------------------------------------------------------
# cert get
# ---------------------------------------------------------------------------

def test_integration_cert_get(monkeypatch, tmp_path: Path) -> None:
    app = _make_server_app(tmp_path)
    _patch_httpx(monkeypatch, app)
    runner.invoke(ctl_module.app, ["cert", "create", "--entry-name", "site-a"])

    result = runner.invoke(ctl_module.app, ["cert", "get", "--entry-name", "site-a"])
    assert result.exit_code == 0
    assert "site-a" in result.output


def test_integration_cert_get_unknown_entry_exits_api_error(monkeypatch, tmp_path: Path) -> None:
    _patch_httpx(monkeypatch, _make_server_app(tmp_path))
    result = runner.invoke(ctl_module.app, ["cert", "get", "--entry-name", "no-such"])
    assert result.exit_code == ctl_module.EXIT_API_ERROR


# ---------------------------------------------------------------------------
# cert renew
# ---------------------------------------------------------------------------

def test_integration_cert_renew(monkeypatch, tmp_path: Path) -> None:
    app = _make_server_app(tmp_path)
    _patch_httpx(monkeypatch, app)
    result = runner.invoke(ctl_module.app, ["cert", "renew", "--entry-name", "site-a"])
    assert result.exit_code == 0
    assert "job_id" in result.output


def test_integration_cert_renew_idempotent(monkeypatch, tmp_path: Path) -> None:
    """Second renew call must return the same job_id (idempotent)."""
    app = _make_server_app(tmp_path)
    _patch_httpx(monkeypatch, app)

    import json as _json
    r1 = runner.invoke(ctl_module.app, ["--output", "json", "cert", "renew", "--entry-name", "site-a"])
    r2 = runner.invoke(ctl_module.app, ["--output", "json", "cert", "renew", "--entry-name", "site-a"])
    d1 = _json.loads(r1.output)
    d2 = _json.loads(r2.output)
    assert r1.exit_code == 0
    assert r2.exit_code == 0
    assert d1["job_id"] == d2["job_id"]
    assert d2["created"] is False


# ---------------------------------------------------------------------------
# job get
# ---------------------------------------------------------------------------

def test_integration_job_get(monkeypatch, tmp_path: Path) -> None:
    app = _make_server_app(tmp_path)
    _patch_httpx(monkeypatch, app)
    create_result = runner.invoke(
        ctl_module.app, ["--output", "json", "cert", "create", "--entry-name", "site-a"]
    )
    import json as _json
    job_id = _json.loads(create_result.output)["job_id"]

    result = runner.invoke(ctl_module.app, ["--output", "json", "job", "get", "--job-id", job_id])
    assert result.exit_code == 0
    data = _json.loads(result.output)
    assert data["job_id"] == job_id
    assert data["status"] == "queued"


def test_integration_job_get_not_found(monkeypatch, tmp_path: Path) -> None:
    _patch_httpx(monkeypatch, _make_server_app(tmp_path))
    result = runner.invoke(ctl_module.app, ["job", "get", "--job-id", "nonexistent"])
    assert result.exit_code == ctl_module.EXIT_API_ERROR


# ---------------------------------------------------------------------------
# job list
# ---------------------------------------------------------------------------

def test_integration_job_list_empty(monkeypatch, tmp_path: Path) -> None:
    _patch_httpx(monkeypatch, _make_server_app(tmp_path))
    result = runner.invoke(ctl_module.app, ["--output", "json", "job", "list"])
    assert result.exit_code == 0
    import json as _json
    assert _json.loads(result.output) == []


def test_integration_job_list_with_filter(monkeypatch, tmp_path: Path) -> None:
    app = _make_server_app(tmp_path)
    _patch_httpx(monkeypatch, app)
    runner.invoke(ctl_module.app, ["cert", "create", "--entry-name", "site-a"])

    result = runner.invoke(
        ctl_module.app,
        ["--output", "json", "job", "list", "--subject-id", "site-a", "--status", "queued"],
    )
    import json as _json
    assert result.exit_code == 0
    items = _json.loads(result.output)
    assert len(items) == 1
    assert items[0]["subject_id"] == "site-a"


# ---------------------------------------------------------------------------
# job wait
# ---------------------------------------------------------------------------

def test_integration_job_wait_terminal(monkeypatch, tmp_path: Path) -> None:
    """If job is already in terminal state, wait returns immediately."""
    from certman.config import resolve_runtime_path
    from certman.services.job_service import JobService

    app = _make_server_app(tmp_path)
    _patch_httpx(monkeypatch, app)

    create_r = runner.invoke(
        ctl_module.app, ["--output", "json", "cert", "create", "--entry-name", "site-a"]
    )
    import json as _json
    job_id = _json.loads(create_r.output)["job_id"]

    # Force job to completed directly via service
    runtime = app.state.runtime
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    service = JobService(db_path=db_path)
    service.update_status(job_id, status="completed", result="ok")

    result = runner.invoke(
        ctl_module.app,
        ["job", "wait", "--job-id", job_id, "--poll-interval", "0.1", "--max-wait", "5"],
    )
    assert result.exit_code == 0
    assert "completed" in result.output


# ---------------------------------------------------------------------------
# webhook create / list / get / update / delete
# ---------------------------------------------------------------------------

def test_integration_webhook_lifecycle(monkeypatch, tmp_path: Path) -> None:
    """Full create → list → get → update → delete lifecycle."""
    import json as _json

    app = _make_server_app(tmp_path)
    _patch_httpx(monkeypatch, app)

    # create
    r_create = runner.invoke(
        ctl_module.app,
        [
            "--output", "json",
            "webhook", "create",
            "--topic", "job.completed",
            "--endpoint-url", "https://example.test/hook",
            "--secret", "mysecret",
        ],
    )
    assert r_create.exit_code == 0
    sub_id = _json.loads(r_create.output)["id"]
    assert sub_id

    # list
    r_list = runner.invoke(ctl_module.app, ["--output", "json", "webhook", "list"])
    assert r_list.exit_code == 0
    items = _json.loads(r_list.output)
    assert len(items) == 1
    assert items[0]["id"] == sub_id

    # list with topic filter
    r_list_f = runner.invoke(
        ctl_module.app, ["--output", "json", "webhook", "list", "--topic", "job.completed"]
    )
    assert r_list_f.exit_code == 0
    assert len(_json.loads(r_list_f.output)) == 1

    # get
    r_get = runner.invoke(ctl_module.app, ["--output", "json", "webhook", "get", "--id", sub_id])
    assert r_get.exit_code == 0
    assert _json.loads(r_get.output)["id"] == sub_id

    # update
    r_update = runner.invoke(
        ctl_module.app,
        ["--output", "json", "webhook", "update", "--id", sub_id, "--status", "inactive"],
    )
    assert r_update.exit_code == 0
    assert _json.loads(r_update.output)["status"] == "inactive"

    # delete
    r_delete = runner.invoke(ctl_module.app, ["webhook", "delete", "--id", sub_id])
    assert r_delete.exit_code == 0

    # confirm deleted
    r_get_gone = runner.invoke(ctl_module.app, ["webhook", "get", "--id", sub_id])
    assert r_get_gone.exit_code == ctl_module.EXIT_API_ERROR


def test_integration_webhook_update_no_fields_exits_1(monkeypatch, tmp_path: Path) -> None:
    _patch_httpx(monkeypatch, _make_server_app(tmp_path))
    result = runner.invoke(ctl_module.app, ["webhook", "update", "--id", "any-id"])
    assert result.exit_code == 1


def test_integration_webhook_delete_not_found(monkeypatch, tmp_path: Path) -> None:
    _patch_httpx(monkeypatch, _make_server_app(tmp_path))
    result = runner.invoke(ctl_module.app, ["webhook", "delete", "--id", "nonexistent"])
    assert result.exit_code == ctl_module.EXIT_API_ERROR
