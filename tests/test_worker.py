from __future__ import annotations

from pathlib import Path

from certman.services.job_service import JobService
from certman.worker import run_once


def test_worker_processes_queued_issue_job(monkeypatch, tmp_path: Path) -> None:
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

    service = JobService(db_path=data_dir / "run" / "certman.db")
    job = service.create_job(job_type="issue", subject_id="site-a")

    class FakeCertService:
        def __init__(self, runtime):
            self.runtime = runtime

        def issue(self, name: str, *, force: bool = False, verbose: bool = False):
            return type(
                "IssueResult",
                (),
                {
                    "success": True,
                    "entry_name": name,
                    "domains": ["example.com"],
                    "log_path": Path("data/log/run.json"),
                    "admin_required": False,
                    "error": None,
                },
            )()

    class FakeDeliveryService:
        def __init__(self, runtime):
            self.runtime = runtime

        def deliver(self, entry_name: str):
            return type(
                "DeliveryResult",
                (),
                {
                    "success": True,
                    "entry_name": entry_name,
                    "executions": [],
                    "error": None,
                },
            )()

    monkeypatch.setattr("certman.worker.CertService", FakeCertService)
    monkeypatch.setattr("certman.worker.DeliveryService", FakeDeliveryService)

    processed = run_once(data_dir=str(data_dir), config_file="config.toml")
    updated = service.get_job(job.job_id)

    assert processed == 1
    assert updated is not None
    assert updated.status == "completed"


def test_worker_marks_job_failed_when_execution_raises(tmp_path: Path) -> None:
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


def test_worker_marks_job_failed_when_delivery_fails(monkeypatch, tmp_path: Path) -> None:
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

    service = JobService(db_path=data_dir / "run" / "certman.db")
    job = service.create_job(job_type="issue", subject_id="site-a")

    class FakeCertService:
        def __init__(self, runtime):
            self.runtime = runtime

        def issue(self, name: str, *, force: bool = False, verbose: bool = False):
            return type(
                "IssueResult",
                (),
                {
                    "success": True,
                    "entry_name": name,
                    "domains": ["example.com"],
                    "log_path": Path("data/log/run.json"),
                    "admin_required": False,
                    "error": None,
                },
            )()

    class BrokenDeliveryService:
        def __init__(self, runtime):
            self.runtime = runtime

        def deliver(self, entry_name: str):
            return type(
                "DeliveryResult",
                (),
                {
                    "success": False,
                    "entry_name": entry_name,
                    "executions": [],
                    "error": "acm import failed",
                },
            )()

    monkeypatch.setattr("certman.worker.CertService", FakeCertService)
    monkeypatch.setattr("certman.worker.DeliveryService", BrokenDeliveryService)

    processed = run_once(data_dir=str(data_dir), config_file="config.toml")
    updated = service.get_job(job.job_id)

    assert processed == 1
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error == "acm import failed"
