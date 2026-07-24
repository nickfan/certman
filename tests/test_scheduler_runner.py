from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from certman.db.engine import make_session_factory
from certman.db.models import CertificateORM
from certman.scheduler.runner import _matches_cron, app, run_once
from certman.services.job_service import JobService


def _write_lineage(data_dir) -> None:
    cert_name = "example.com"
    letsencrypt_dir = data_dir / "run" / "letsencrypt"
    renewal_dir = letsencrypt_dir / "renewal"
    live_dir = letsencrypt_dir / "live" / cert_name
    renewal_dir.mkdir(parents=True, exist_ok=True)
    live_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / f"{cert_name}.conf").write_text("# test lineage\n", encoding="utf-8")
    (live_dir / "cert.pem").write_text("test certificate", encoding="utf-8")


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

    def fake_schedule_due_renewals(*, db_path, now=None, renew_before_days=30, target_scope=None, entry_targets=None, event_bus=None):
        observed["db_path"] = db_path
        observed["renew_before_days"] = renew_before_days
        observed["target_scope"] = target_scope
        observed["entry_targets"] = entry_targets
        return [object(), object()]

    monkeypatch.setattr("certman.scheduler.runner.schedule_due_renewals", fake_schedule_due_renewals)

    result = run_once(data_dir=str(tmp_path), config_file="config.toml")

    assert result == 2
    assert observed["renew_before_days"] == 18
    assert observed["target_scope"] is None
    assert isinstance(observed["entry_targets"], dict)


def test_run_once_reconciles_existing_lineage_before_scheduling(monkeypatch, tmp_path) -> None:
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

[scheduler]
enabled = true
renew_before_days = 30
""".strip(),
        encoding="utf-8",
    )
    expected_not_after = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)
    _write_lineage(data_dir)
    status = type("CertStatus", (), {"not_after": expected_not_after})()
    monkeypatch.setattr(
        "certman.services.certificate_inventory_service.get_cert_status",
        lambda cert_path: status,
    )

    result = run_once(data_dir=str(data_dir), config_file="config.toml")

    db_path = data_dir / "run" / "certman.db"
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        certificate = session.query(CertificateORM).one()
    jobs = JobService(db_path=db_path).list_jobs(subject_id="site-a")
    assert result == 1
    assert certificate.not_after == expected_not_after.replace(tzinfo=None)
    assert len(jobs) == 1
    assert jobs[0].job_type == "renew"
    assert jobs[0].status == "queued"


def test_matches_cron_requires_five_fields() -> None:
    now = datetime(2026, 3, 27, 10, 15, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="exactly 5 fields"):
        _matches_cron("*/5 * * *", now)


def test_once_command_delegates_to_run_once(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run_once(
        *,
        data_dir: str,
        config_file: str | None,
        force_enable: bool,
        renew_before_days: int | None,
        target_scope: str | None,
    ):
        observed["data_dir"] = data_dir
        observed["config_file"] = config_file
        observed["force_enable"] = force_enable
        observed["renew_before_days"] = renew_before_days
        observed["target_scope"] = target_scope
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
            "--target-scope",
            "office",
        ],
    )

    assert result.exit_code == 0
    assert observed["data_dir"] == "data"
    assert observed["config_file"] == "config.toml"
    assert observed["force_enable"] is True
    assert observed["renew_before_days"] == 21
    assert observed["target_scope"] == "office"
