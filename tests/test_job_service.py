from __future__ import annotations

import sqlite3
from pathlib import Path

from certman.services.job_service import JobService


def test_job_service_creates_and_reads_job(tmp_path: Path) -> None:
    service = JobService(db_path=tmp_path / "certman.db")

    job = service.create_job(job_type="issue", subject_id="site-a", target_type="nginx", target_scope="office")
    fetched = service.get_job(job.job_id)

    assert fetched is not None
    assert fetched.job_id == job.job_id
    assert fetched.status == "queued"
    assert fetched.target_type == "nginx"
    assert fetched.target_scope == "office"


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


def test_job_service_list_jobs_supports_target_scope(tmp_path: Path) -> None:
    service = JobService(db_path=tmp_path / "certman.db")
    service.create_job(job_type="issue", subject_id="site-a", target_scope="office")
    service.create_job(job_type="issue", subject_id="site-b", target_scope="prod")

    office_jobs = service.list_jobs(target_scope="office")

    assert len(office_jobs) == 1
    assert office_jobs[0].subject_id == "site-a"


def test_enqueue_unique_job_reuses_running_job(tmp_path: Path) -> None:
    service = JobService(db_path=tmp_path / "certman.db")
    first = service.create_job(job_type="renew", subject_id="site-a")
    service.update_status(first.job_id, status="running")

    second, created = service.enqueue_unique_job(job_type="renew", subject_id="site-a")

    assert created is False
    assert second.job_id == first.job_id


def test_claim_next_job_reclaims_expired_running_job(tmp_path: Path) -> None:
    service = JobService(db_path=tmp_path / "certman.db")
    stale = service.create_job(job_type="renew", subject_id="site-a")
    service.update_status(stale.job_id, status="running")
    queued = service.create_job(job_type="renew", subject_id="site-b")
    with sqlite3.connect(tmp_path / "certman.db") as db:
        db.execute("UPDATE job SET updated_at = '2020-01-01 00:00:00' WHERE job_id = ?", (stale.job_id,))
        db.commit()

    claimed = service.claim_next_job()

    assert claimed is not None
    assert claimed.job_id == queued.job_id
    assert service.get_job(stale.job_id).status == "failed"


def test_terminal_jobs_can_share_type_subject(tmp_path: Path) -> None:
    service = JobService(db_path=tmp_path / "certman.db")
    first = service.create_job(job_type="issue", subject_id="site-a")
    service.update_status(first.job_id, status="completed", result="ok")
    second = service.create_job(job_type="issue", subject_id="site-a")
    service.update_status(second.job_id, status="completed", result="ok")

    assert service.get_job(second.job_id).status == "completed"
