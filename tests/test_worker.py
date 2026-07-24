from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from certman.db.engine import make_session_factory
from certman.db.models import CertificateORM
from certman.services.job_service import JobService
from certman.worker import run_once


def _write_server_config(data_dir: Path) -> None:
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


def _write_lineage(runtime) -> None:
    cert_name = "example.com"
    letsencrypt_dir = runtime.paths.run_dir / runtime.config.global_.letsencrypt_dir
    renewal_dir = letsencrypt_dir / "renewal"
    live_dir = letsencrypt_dir / "live" / cert_name
    renewal_dir.mkdir(parents=True, exist_ok=True)
    live_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / f"{cert_name}.conf").write_text("# test lineage\n", encoding="utf-8")
    (live_dir / "cert.pem").write_text("test certificate", encoding="utf-8")


def _set_certificate_not_after(monkeypatch, not_after: datetime) -> None:
    status = type("CertStatus", (), {"not_after": not_after})()
    monkeypatch.setattr(
        "certman.services.certificate_inventory_service.get_cert_status",
        lambda cert_path: status,
    )


def _certificate_rows(db_path: Path) -> list[CertificateORM]:
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        return list(session.query(CertificateORM).order_by(CertificateORM.entry_name).all())


class _SuccessfulIssueService:
    def __init__(self, runtime):
        self.runtime = runtime

    def issue(self, name: str, *, force: bool = False, verbose: bool = False):
        _write_lineage(self.runtime)
        return SimpleNamespace(
            success=True,
            entry_name=name,
            domains=["example.com"],
            log_path=Path("data/log/run.json"),
            admin_required=False,
            error=None,
        )


class _SuccessfulRenewService:
    def __init__(self, runtime):
        self.runtime = runtime

    def renew(self, **kwargs):
        _write_lineage(self.runtime)
        return [SimpleNamespace(success=True, error=None)]


class _SuccessfulDeliveryService:
    def __init__(self, runtime):
        self.runtime = runtime

    def deliver(self, entry_name: str):
        return SimpleNamespace(success=True, entry_name=entry_name, executions=[], error=None)


class _FailingDeliveryService:
    def __init__(self, runtime):
        self.runtime = runtime

    def deliver(self, entry_name: str):
        return SimpleNamespace(
            success=False,
            entry_name=entry_name,
            executions=[],
            error="acm import failed",
        )


def test_worker_processes_queued_issue_job(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_server_config(data_dir)

    service = JobService(db_path=data_dir / "run" / "certman.db")
    job = service.create_job(job_type="issue", subject_id="site-a")

    monkeypatch.setattr("certman.worker.CertService", _SuccessfulIssueService)
    monkeypatch.setattr("certman.worker.DeliveryService", _SuccessfulDeliveryService)
    _set_certificate_not_after(
        monkeypatch,
        datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=90),
    )

    processed = run_once(data_dir=str(data_dir), config_file="config.toml")
    updated = service.get_job(job.job_id)

    assert processed == 1
    assert updated is not None
    assert updated.status == "completed"


def test_worker_records_certificate_after_successful_issue(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_server_config(data_dir)
    db_path = data_dir / "run" / "certman.db"
    job_service = JobService(db_path=db_path)
    job_service.create_job(job_type="issue", subject_id="site-a")
    expected_not_after = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=90)

    monkeypatch.setattr("certman.worker.CertService", _SuccessfulIssueService)
    monkeypatch.setattr("certman.worker.DeliveryService", _SuccessfulDeliveryService)
    _set_certificate_not_after(monkeypatch, expected_not_after)

    run_once(data_dir=str(data_dir), config_file="config.toml")

    rows = _certificate_rows(db_path)
    assert len(rows) == 1
    assert rows[0].entry_name == "site-a"
    assert rows[0].primary_domain == "example.com"
    assert rows[0].status == "active"
    assert rows[0].not_after == expected_not_after.replace(tzinfo=None)


def test_worker_updates_certificate_after_successful_renew(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_server_config(data_dir)
    db_path = data_dir / "run" / "certman.db"
    job_service = JobService(db_path=db_path)
    job_service.create_job(job_type="renew", subject_id="site-a")
    old_not_after = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)
    new_not_after = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=90)
    session_factory = make_session_factory(db_path)
    with session_factory() as session:
        session.add(
            CertificateORM(
                id="existing-cert",
                entry_name="site-a",
                primary_domain="example.com",
                status="active",
                not_after=old_not_after,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    monkeypatch.setattr("certman.worker.CertService", _SuccessfulRenewService)
    monkeypatch.setattr("certman.worker.DeliveryService", _SuccessfulDeliveryService)
    _set_certificate_not_after(monkeypatch, new_not_after)

    run_once(data_dir=str(data_dir), config_file="config.toml")

    rows = _certificate_rows(db_path)
    assert len(rows) == 1
    assert rows[0].id == "existing-cert"
    assert rows[0].not_after == new_not_after.replace(tzinfo=None)


def test_worker_marks_job_failed_when_execution_raises(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_server_config(data_dir)

    service = JobService(db_path=data_dir / "run" / "certman.db")
    job = service.create_job(job_type="issue", subject_id="site-a")

    class BrokenCertService:
        def __init__(self, runtime):
            self.runtime = runtime

        def issue(self, name: str, *, force: bool = False, verbose: bool = False):
            raise ValueError("boom")

    from certman import worker as worker_module

    original = worker_module.CertService
    worker_module.CertService = BrokenCertService
    try:
        processed = run_once(data_dir=str(data_dir), config_file="config.toml")
    finally:
        worker_module.CertService = original

    updated = service.get_job(job.job_id)

    assert processed == 1
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error == "boom"


def test_worker_keeps_issued_certificate_inventory_when_delivery_fails(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_server_config(data_dir)

    service = JobService(db_path=data_dir / "run" / "certman.db")
    job = service.create_job(job_type="issue", subject_id="site-a")
    expected_not_after = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=90)

    monkeypatch.setattr("certman.worker.CertService", _SuccessfulIssueService)
    monkeypatch.setattr("certman.worker.DeliveryService", _FailingDeliveryService)
    _set_certificate_not_after(monkeypatch, expected_not_after)

    processed = run_once(data_dir=str(data_dir), config_file="config.toml")
    updated = service.get_job(job.job_id)

    assert processed == 1
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error == "acm import failed"
    rows = _certificate_rows(data_dir / "run" / "certman.db")
    assert len(rows) == 1
    assert rows[0].entry_name == "site-a"
    assert rows[0].not_after == expected_not_after.replace(tzinfo=None)
