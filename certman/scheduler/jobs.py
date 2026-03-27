from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from certman.db.engine import make_session_factory
from certman.db.models import CertificateORM
from certman.events import EventBus
from certman.models.job import JobRecord
from certman.node_agent.subscribe_bus import notify_assignment_candidates_updated
from certman.services.job_service import JobService


def schedule_due_renewals(
    *,
    db_path: str | Path,
    now: datetime | None = None,
    renew_before_days: int = 30,
    target_scope: str | None = None,
    entry_targets: dict[str, tuple[str, str | None]] | None = None,
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
            target_type = "generic"
            certificate_scope: str | None = None
            if entry_targets is not None and certificate.entry_name in entry_targets:
                target_type, certificate_scope = entry_targets[certificate.entry_name]

            if target_scope is not None and certificate_scope != target_scope:
                continue

            job, created = service.enqueue_unique_job(
                job_type="renew",
                subject_id=certificate.entry_name,
                target_type=target_type,
                target_scope=certificate_scope,
            )
            if not created:
                continue
            created_jobs.append(job)
            notify_assignment_candidates_updated()
            if event_bus is not None:
                event_bus.publish("job.queued", job.model_dump())

    return created_jobs