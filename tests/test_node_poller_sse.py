from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from certman.node_agent.poller import NodePoller
from certman.security.identity import generate_ed25519_keypair


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeStreamResponse:
    def __init__(self, status_code: int, lines: list[str]):
        self.status_code = status_code
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_lines(self):
        for line in self._lines:
            yield line


def _make_poller(tmp_path: Path, *, prefer_sse: bool = True, prefer_subscribe: bool = True) -> NodePoller:
    key_dir = tmp_path / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    private_key = key_dir / "node-a.pem"
    public_key = key_dir / "node-a.pub.pem"
    generate_ed25519_keypair(private_key, public_key)
    return NodePoller(
        endpoint="https://certman.example.com",
        node_id="node-a",
        private_key_path=private_key,
        public_key_path=public_key,
        prefer_sse=prefer_sse,
        sse_wait_seconds=1,
        prefer_subscribe=prefer_subscribe,
        subscribe_wait_seconds=1,
    )


def test_poller_prefers_sse_when_assignment_available(monkeypatch, tmp_path: Path) -> None:
    poller = _make_poller(tmp_path)

    monkeypatch.setattr(
        "certman.node_agent.poller.NodePoller.ensure_registered",
        lambda self: self.last_registration,
    )

    def fake_stream(method: str, url: str, params=None, timeout=None):
        del method, url, params, timeout
        return _FakeStreamResponse(
            200,
            [
                "event: connected",
                "data: {}",
                "",
                "event: assignment",
                'data: {"assignments":[{"job_id":"job-sse","job_type":"renew","bundle_url":"/api/v1/node-agent/bundles/job-sse"}]}',
                "",
            ],
        )

    monkeypatch.setattr("certman.node_agent.poller.httpx.stream", fake_stream)

    def fake_post(url: str, json: dict, timeout: int, params=None):
        del json, timeout, params
        if url.endswith("/api/v1/node-agent/subscribe"):
            raise AssertionError("subscribe should not be called when SSE already has assignment")
        if url.endswith("/api/v1/node-agent/poll"):
            raise AssertionError("poll should not be called when SSE already has assignment")
        return _FakeResponse(404, {"success": False})

    monkeypatch.setattr("certman.node_agent.poller.httpx.post", fake_post)

    assignments = poller.poll()
    assert len(assignments) == 1
    assert assignments[0]["job_id"] == "job-sse"


def test_poller_fallback_to_subscribe_when_sse_unavailable(monkeypatch, tmp_path: Path) -> None:
    poller = _make_poller(tmp_path)

    monkeypatch.setattr(
        "certman.node_agent.poller.NodePoller.ensure_registered",
        lambda self: self.last_registration,
    )

    def fake_stream(method: str, url: str, params=None, timeout=None):
        del method, url, params, timeout
        return _FakeStreamResponse(404, [])

    monkeypatch.setattr("certman.node_agent.poller.httpx.stream", fake_stream)

    def fake_post(url: str, json: dict, timeout: int, params=None):
        del timeout
        if url.endswith("/api/v1/node-agent/subscribe"):
            assert params is not None
            return _FakeResponse(
                200,
                {
                    "success": True,
                    "data": {
                        "assignments": [
                            {
                                "job_id": "job-subscribe",
                                "job_type": "renew",
                                "bundle_url": "/api/v1/node-agent/bundles/job-subscribe",
                            }
                        ]
                    },
                },
            )
        if url.endswith("/api/v1/node-agent/poll"):
            raise AssertionError("poll should not be called when subscribe fallback succeeds")
        return _FakeResponse(404, {"success": False})

    monkeypatch.setattr("certman.node_agent.poller.httpx.post", fake_post)

    assignments = poller.poll()
    assert len(assignments) == 1
    assert assignments[0]["job_id"] == "job-subscribe"
