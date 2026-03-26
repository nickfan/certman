from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from certman.mcp_server import McpServerConfig, _call_api, _parse_api_response


def test_parse_api_response_success_envelope() -> None:
    body = {"success": True, "data": {"job_id": "abc"}}
    assert _parse_api_response(status_code=200, body=body) == {"job_id": "abc"}


def test_parse_api_response_error_envelope() -> None:
    body = {"success": False, "error": {"code": "NOT_FOUND", "message": "missing"}}
    with pytest.raises(RuntimeError, match="API_ERROR:NOT_FOUND:missing"):
        _parse_api_response(status_code=404, body=body)


def test_parse_api_response_non_envelope_http_error() -> None:
    with pytest.raises(RuntimeError, match="API_ERROR:HTTP_500:request failed"):
        _parse_api_response(status_code=500, body={"detail": "bad"})


def test_parse_api_response_plain_payload() -> None:
    payload = {"status": "ok"}
    assert _parse_api_response(status_code=200, body=payload) == payload


def test_call_api_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_request_error(**_: object) -> object:
        request = httpx.Request("GET", "http://127.0.0.1:8000/health")
        raise httpx.RequestError("boom", request=request)

    monkeypatch.setattr(httpx, "request", _raise_request_error)
    config = McpServerConfig(
        endpoint="http://127.0.0.1:8000",
        timeout=1.0,
        token=None,
        poll_interval=1.0,
        max_wait=1.0,
    )

    with pytest.raises(ConnectionError, match="NETWORK_ERROR"):
        _call_api(method="GET", path="/health", config=config)


def test_call_api_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse(SimpleNamespace):
        def json(self) -> dict[str, str]:
            raise ValueError("bad json")

    def _mock_request(**_: object) -> _FakeResponse:
        return _FakeResponse(status_code=200)

    monkeypatch.setattr(httpx, "request", _mock_request)
    config = McpServerConfig(
        endpoint="http://127.0.0.1:8000",
        timeout=1.0,
        token=None,
        poll_interval=1.0,
        max_wait=1.0,
    )

    with pytest.raises(RuntimeError, match="API_ERROR:INVALID_JSON"):
        _call_api(method="GET", path="/health", config=config)
