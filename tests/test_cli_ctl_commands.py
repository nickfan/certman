from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
from typer.testing import CliRunner

from certman.ctl.cli import _call_api, app


runner = CliRunner()


def test_ctl_cli_top_help_contains_positioning() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "control-plane CLI client" in result.stdout
    assert "--endpoint" in result.stdout
    assert "--timeout" in result.stdout
    assert "--output" in result.stdout


def test_ctl_job_wait_help_contains_key_options() -> None:
    result = runner.invoke(app, ["job", "wait", "--help"])

    assert result.exit_code == 0
    assert "--job-id" in result.stdout
    assert "--poll-interval" in result.stdout
    assert "--max-wait" in result.stdout


def test_ctl_health_text_success(monkeypatch) -> None:
    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None):
        assert method == "GET"
        assert path == "/health"
        return {"status": "ok"}

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 0
    assert "status=ok" in result.stdout


def test_ctl_cert_create_json_success(monkeypatch) -> None:
    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None):
        assert method == "POST"
        assert path == "/api/v1/certificates"
        assert payload == {"entry_name": "site-a"}
        return {"job_id": "job-123"}

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(app, ["--output", "json", "cert", "create", "--entry-name", "site-a"])

    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["job_id"] == "job-123"


def test_ctl_job_get_server_error_maps_exit_4(monkeypatch) -> None:
    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None):
        raise RuntimeError("API_ERROR:NOT_FOUND_JOB:job not found")

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(app, ["job", "get", "--job-id", "missing"])

    assert result.exit_code == 4
    assert "NOT_FOUND_JOB" in result.stdout


def test_ctl_webhook_create_network_error_maps_exit_3(monkeypatch) -> None:
    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None):
        raise ConnectionError("NETWORK_ERROR:connection refused")

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(
        app,
        [
            "webhook",
            "create",
            "--topic",
            "job.completed",
            "--endpoint-url",
            "https://example.test/hook",
            "--secret",
            "topsecret",
        ],
    )

    assert result.exit_code == 3
    assert "NETWORK_ERROR" in result.stdout


def test_ctl_health_uses_token_and_endpoint(monkeypatch) -> None:
    observed: dict[str, str | float | None] = {}

    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None):
        observed["endpoint"] = endpoint
        observed["timeout"] = timeout
        observed["token"] = token
        return {"status": "ok"}

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(
        app,
        [
            "--endpoint",
            "http://127.0.0.1:19000",
            "--timeout",
            "3",
            "--token",
            "abc",
            "health",
        ],
    )

    assert result.exit_code == 0
    assert observed == {
        "endpoint": "http://127.0.0.1:19000",
        "timeout": 3.0,
        "token": "abc",
    }


def test_call_api_parses_enveloped_error(monkeypatch) -> None:
    response = SimpleNamespace(
        status_code=404,
        json=lambda: {
            "success": False,
            "data": None,
            "error": {"code": "NOT_FOUND_JOB", "message": "job not found"},
        },
    )
    monkeypatch.setattr("certman.ctl.cli.httpx.request", lambda **kwargs: response)

    try:
        _call_api(
            method="GET",
            path="/api/v1/jobs/missing",
            endpoint="http://127.0.0.1:8000",
            timeout=3,
            token=None,
        )
    except RuntimeError as exc:
        assert str(exc) == "API_ERROR:NOT_FOUND_JOB:job not found"
    else:
        raise AssertionError("expected RuntimeError")


def test_call_api_maps_request_error_to_network_error(monkeypatch) -> None:
    request = httpx.Request("GET", "http://127.0.0.1:8000/health")

    def fake_request(**kwargs):
        raise httpx.ConnectError("boom", request=request)

    monkeypatch.setattr("certman.ctl.cli.httpx.request", fake_request)

    try:
        _call_api(
            method="GET",
            path="/health",
            endpoint="http://127.0.0.1:8000",
            timeout=3,
            token=None,
        )
    except ConnectionError as exc:
        assert str(exc).startswith("NETWORK_ERROR:")
    else:
        raise AssertionError("expected ConnectionError")


def test_ctl_cert_get_url_encodes_entry_name(monkeypatch) -> None:
    observed: dict[str, str] = {}

    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None, params=None):
        observed["method"] = method
        observed["path"] = path
        return [{"job_id": "job-1"}]

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(app, ["cert", "get", "--entry-name", "site/a b"])

    assert result.exit_code == 0
    assert observed == {
        "method": "GET",
        "path": "/api/v1/certificates/site%2Fa%20b",
    }


def test_ctl_job_list_uses_query_params_dict(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None, params=None):
        observed["method"] = method
        observed["path"] = path
        observed["params"] = params
        return []

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(
        app,
        ["job", "list", "--subject-id", "a&b", "--status", "running", "--limit", "7"],
    )

    assert result.exit_code == 0
    assert observed == {
        "method": "GET",
        "path": "/api/v1/jobs",
        "params": {"subject_id": "a&b", "status": "running", "limit": 7},
    }


def test_ctl_config_list_calls_readonly_endpoint(monkeypatch) -> None:
    observed: dict[str, str] = {}

    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None, params=None):
        observed["method"] = method
        observed["path"] = path
        return []

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(app, ["config", "list"])

    assert result.exit_code == 0
    assert observed == {"method": "GET", "path": "/api/v1/config/entries"}


def test_ctl_config_show_url_encodes_entry_name(monkeypatch) -> None:
    observed: dict[str, str] = {}

    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None, params=None):
        observed["method"] = method
        observed["path"] = path
        return {"name": "site-a"}

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(app, ["config", "show", "--entry-name", "site/a b"])

    assert result.exit_code == 0
    assert observed == {
        "method": "GET",
        "path": "/api/v1/config/entries/site%2Fa%20b",
    }


def test_ctl_config_validate_payload(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_call(*, method: str, path: str, endpoint: str, timeout: float, token: str | None, payload=None, params=None):
        observed["method"] = method
        observed["path"] = path
        observed["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr("certman.ctl.cli._call_api", fake_call)

    result = runner.invoke(app, ["config", "validate", "--entry-name", "site-a", "--entry-name", "site-b"])

    assert result.exit_code == 0
    assert observed == {
        "method": "POST",
        "path": "/api/v1/config/validate",
        "payload": {"entry_names": ["site-a", "site-b"], "validate_all": False},
    }
