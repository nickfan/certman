from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from certman.node_agent.agent import app
from certman.security.identity import generate_ed25519_keypair


def test_agent_mode_runs_empty_poll_once(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.toml").write_text(
        """
run_mode = "agent"

[global]
data_dir = "data"
email = "ops@example.com"

[control_plane]
endpoint = "https://certman.example.com"
poll_interval_seconds = 15

[node_identity]
node_id = "node-a"
private_key_path = "keys/node-a.pem"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr("certman.node_agent.agent.NodePoller.poll", lambda self: [])

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.toml",
            "--once",
        ],
    )

    assert result.exit_code == 0
    assert "node_id=node-a" in result.stdout
    assert "poll_count=0" in result.stdout


def test_agent_mode_registers_before_poll(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    key_dir = tmp_path / "keys"
    conf_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)

    private_key_path = key_dir / "node-a.pem"
    public_key_path = key_dir / "node-a.pub.pem"
    generate_ed25519_keypair(private_key_path, public_key_path)

    (conf_dir / "config.toml").write_text(
        """
run_mode = "agent"

[global]
data_dir = "data"
email = "ops@example.com"

[control_plane]
endpoint = "https://certman.example.com"
poll_interval_seconds = 15

[node_identity]
node_id = "node-a"
private_key_path = "keys/node-a.pem"
public_key_path = "keys/node-a.pub.pem"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CERTMAN_NODE_REGISTRATION_TOKEN", "reg-token")

    calls: list[str] = []

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fake_post(url: str, json: dict, timeout: int):
        del timeout
        if url.endswith("/api/v1/nodes/register"):
            calls.append("register")
            assert json["node_id"] == "node-a"
            assert json["register_token"] == "reg-token"
            return FakeResponse(201, {"success": True, "data": {"node_id": "node-a"}})
        if url.endswith("/api/v1/node-agent/poll"):
            calls.append("poll")
            return FakeResponse(200, {"success": True, "data": {"assignments": []}})
        return FakeResponse(404, {"success": False})

    monkeypatch.setattr("certman.node_agent.poller.httpx.post", fake_post)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.toml",
            "--once",
        ],
    )

    assert result.exit_code == 0
    assert calls == ["register", "poll"]


def test_agent_mode_registration_non_retryable_failure_exit_code_2(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    key_dir = tmp_path / "keys"
    conf_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)

    private_key_path = key_dir / "node-a.pem"
    public_key_path = key_dir / "node-a.pub.pem"
    generate_ed25519_keypair(private_key_path, public_key_path)

    (conf_dir / "config.toml").write_text(
        """
run_mode = "agent"

[global]
data_dir = "data"
email = "ops@example.com"

[control_plane]
endpoint = "https://certman.example.com"
poll_interval_seconds = 15

[node_identity]
node_id = "node-a"
private_key_path = "keys/node-a.pem"
public_key_path = "keys/node-a.pub.pem"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CERTMAN_NODE_REGISTRATION_TOKEN", "reg-token")

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fake_post(url: str, json: dict, timeout: int):
        del json, timeout
        if url.endswith("/api/v1/nodes/register"):
            return FakeResponse(401, {"error": {"code": "AUTH_INVALID_REGISTRATION_TOKEN", "message": "invalid"}})
        return FakeResponse(200, {"data": {"assignments": []}})

    monkeypatch.setattr("certman.node_agent.poller.httpx.post", fake_post)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--data-dir", str(data_dir), "--config-file", "config.toml", "--once"],
    )

    assert result.exit_code == 2
    assert "register_status=failed" in result.stdout
    assert "retryable=false" in result.stdout
    assert "register_code=AUTH_INVALID_REGISTRATION_TOKEN" in result.stdout


def test_agent_mode_registration_retryable_failure_exit_code_3(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    key_dir = tmp_path / "keys"
    conf_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)

    private_key_path = key_dir / "node-a.pem"
    public_key_path = key_dir / "node-a.pub.pem"
    generate_ed25519_keypair(private_key_path, public_key_path)

    (conf_dir / "config.toml").write_text(
        """
run_mode = "agent"

[global]
data_dir = "data"
email = "ops@example.com"

[control_plane]
endpoint = "https://certman.example.com"
poll_interval_seconds = 15

[node_identity]
node_id = "node-a"
private_key_path = "keys/node-a.pem"
public_key_path = "keys/node-a.pub.pem"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CERTMAN_NODE_REGISTRATION_TOKEN", "reg-token")

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fake_post(url: str, json: dict, timeout: int):
        del json, timeout
        if url.endswith("/api/v1/nodes/register"):
            return FakeResponse(503, {"error": {"code": "REGISTER_TEMP_UNAVAILABLE", "message": "try later"}})
        return FakeResponse(200, {"data": {"assignments": []}})

    monkeypatch.setattr("certman.node_agent.poller.httpx.post", fake_post)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--data-dir", str(data_dir), "--config-file", "config.toml", "--once"],
    )

    assert result.exit_code == 3
    assert "register_status=failed" in result.stdout
    assert "retryable=true" in result.stdout
    assert "register_code=REGISTER_TEMP_UNAVAILABLE" in result.stdout
