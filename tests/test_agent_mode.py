from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from certman.node_agent.agent import app


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
