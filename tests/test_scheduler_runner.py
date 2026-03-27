from __future__ import annotations

from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from certman.scheduler.runner import _matches_cron, app, run_once


def test_matches_cron_supports_step_and_exact_time() -> None:
    now = datetime(2026, 3, 27, 10, 15, tzinfo=timezone.utc)
    assert _matches_cron("*/5 * * * *", now) is True
    assert _matches_cron("0 * * * *", now) is False
    assert _matches_cron("15 10 * * *", now) is True


def test_run_once_returns_zero_when_scheduler_disabled(tmp_path) -> None:
    conf_dir = tmp_path / "conf"
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

[scheduler]
enabled = false
""".strip(),
        encoding="utf-8",
    )

    result = run_once(data_dir=str(tmp_path), config_file="config.toml")

    assert result == 0


def test_run_once_calls_schedule_due_renewals(monkeypatch, tmp_path) -> None:
    conf_dir = tmp_path / "conf"
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

[scheduler]
enabled = true
renew_before_days = 18
""".strip(),
        encoding="utf-8",
    )

    observed: dict[str, object] = {}

    def fake_schedule_due_renewals(*, db_path, now=None, renew_before_days=30, event_bus=None):
        observed["db_path"] = db_path
        observed["renew_before_days"] = renew_before_days
        return [object(), object()]

    monkeypatch.setattr("certman.scheduler.runner.schedule_due_renewals", fake_schedule_due_renewals)

    result = run_once(data_dir=str(tmp_path), config_file="config.toml")

    assert result == 2
    assert observed["renew_before_days"] == 18


def test_matches_cron_requires_five_fields() -> None:
    now = datetime(2026, 3, 27, 10, 15, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="exactly 5 fields"):
        _matches_cron("*/5 * * *", now)


def test_once_command_delegates_to_run_once(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run_once(*, data_dir: str, config_file: str | None, force_enable: bool, renew_before_days: int | None):
        observed["data_dir"] = data_dir
        observed["config_file"] = config_file
        observed["force_enable"] = force_enable
        observed["renew_before_days"] = renew_before_days
        return 1

    monkeypatch.setattr("certman.scheduler.runner.run_once", fake_run_once)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "once",
            "--data-dir",
            "data",
            "--config-file",
            "config.toml",
            "--force-enable",
            "--renew-before-days",
            "21",
        ],
    )

    assert result.exit_code == 0
    assert observed["data_dir"] == "data"
    assert observed["config_file"] == "config.toml"
    assert observed["force_enable"] is True
    assert observed["renew_before_days"] == 21
