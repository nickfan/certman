from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from certman.db.engine import make_session_factory
from certman.db.models import CertificateORM
from certman.events import EventBus
from certman.models.job import JobRecord
from certman.services.job_service import JobService


def schedule_due_renewals(
    *,
    db_path: str | Path,
    now: datetime | None = None,
    renew_before_days: int = 30,
    event_bus: EventBus | None = None,
) -> list[JobRecord]:
    current_time = now or datetime.now(timezone.utc)
    deadline = current_time + timedelta(days=renew_before_days)
    session_factory = make_session_factory(db_path)
    service = JobService(db_path=db_path)
    created_jobs: list[JobRecord] = []

    with session_factory() as session:
        certificates = (
            session.query(CertificateORM)
            .filter(CertificateORM.status == "active")
            .filter(CertificateORM.not_after.is_not(None))
            .filter(CertificateORM.not_after <= deadline)
            .all()
        )

        for certificate in certificates:
            job, created = service.enqueue_unique_job(job_type="renew", subject_id=certificate.entry_name)
            if not created:
                continue
            created_jobs.append(job)
            if event_bus is not None:
                event_bus.publish("job.queued", job.model_dump())

    return created_jobs