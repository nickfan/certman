from __future__ import annotations

from pathlib import Path

from certman.services.job_service import JobService


def test_job_service_creates_and_reads_job(tmp_path: Path) -> None:
    service = JobService(db_path=tmp_path / "certman.db")

    job = service.create_job(job_type="issue", subject_id="site-a")
    fetched = service.get_job(job.job_id)

    assert fetched is not None
    assert fetched.job_id == job.job_id
    assert fetched.status == "queued"


def test_job_service_updates_job_status(tmp_path: Path) -> None:
    service = JobService(db_path=tmp_path / "certman.db")

    job = service.create_job(job_type="issue", subject_id="site-a")
    updated = service.update_status(job.job_id, status="completed", result="ok")

    assert updated is not None
    assert updated.status == "completed"
    assert updated.result == "ok"


def test_job_service_claims_next_job(tmp_path: Path) -> None:
    service = JobService(db_path=tmp_path / "certman.db")
    service.create_job(job_type="issue", subject_id="site-a")

    claimed = service.claim_next_job()

    assert claimed is not None
    assert claimed.status == "running"


def test_job_service_enqueue_unique_job_avoids_duplicates(tmp_path: Path) -> None:
    service = JobService(db_path=tmp_path / "certman.db")

    first, created_first = service.enqueue_unique_job(job_type="renew", subject_id="site-a")
    second, created_second = service.enqueue_unique_job(job_type="renew", subject_id="site-a")

    assert created_first is True
    assert created_second is False
    assert first.job_id == second.job_id
