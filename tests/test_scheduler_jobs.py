from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from certman.db.engine import make_session_factory
from certman.db.models import CertificateORM
from certman.events import EventBus
from certman.scheduler.jobs import schedule_due_renewals
from certman.services.job_service import JobService


def _insert_certificate(db_path: Path, *, entry_name: str, days_left: int) -> None:
    session_factory = make_session_factory(db_path)
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        session.add(
            CertificateORM(
                id=f"cert-{entry_name}",
                entry_name=entry_name,
                primary_domain=f"{entry_name}.example.com",
                status="active",
                not_after=now + timedelta(days=days_left),
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


def test_schedule_due_renewals_creates_job_for_expiring_certificate(tmp_path: Path) -> None:
    db_path = tmp_path / "certman.db"
    JobService(db_path=db_path)
    _insert_certificate(db_path, entry_name="site-a", days_left=5)

    created_jobs = schedule_due_renewals(db_path=db_path, now=datetime.now(timezone.utc), renew_before_days=30)

    assert len(created_jobs) == 1
    assert created_jobs[0].job_type == "renew"
    assert created_jobs[0].subject_id == "site-a"


def test_schedule_due_renewals_skips_duplicate_queued_job(tmp_path: Path) -> None:
    db_path = tmp_path / "certman.db"
    service = JobService(db_path=db_path)
    _insert_certificate(db_path, entry_name="site-a", days_left=5)
    service.create_job(job_type="renew", subject_id="site-a")

    created_jobs = schedule_due_renewals(db_path=db_path, now=datetime.now(timezone.utc), renew_before_days=30)

    assert created_jobs == []


def test_schedule_due_renewals_publishes_event(tmp_path: Path) -> None:
    db_path = tmp_path / "certman.db"
    JobService(db_path=db_path)
    _insert_certificate(db_path, entry_name="site-a", days_left=5)
    bus = EventBus()
    events: list[dict] = []
    bus.subscribe("job.queued", lambda event: events.append(event.payload))

    schedule_due_renewals(
        db_path=db_path,
        now=datetime.now(timezone.utc),
        renew_before_days=30,
        event_bus=bus,
    )

    assert events[0]["job_type"] == "renew"
    assert events[0]["subject_id"] == "site-a"