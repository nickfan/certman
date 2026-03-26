from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from certman.db.engine import make_engine, make_session_factory
from certman.db.models import Base, JobORM
from certman.models.job import JobRecord


class JobService:
    def __init__(self, *, db_path: str | Path):
        self._db_path = Path(db_path)
        self._engine = make_engine(self._db_path)
        Base.metadata.create_all(self._engine)
        self._session_factory = make_session_factory(self._db_path)

    def create_job(self, *, job_type: str, subject_id: str, node_id: str | None = None) -> JobRecord:
        job = JobORM(
            job_id=uuid4().hex[:12],
            job_type=job_type,
            subject_id=subject_id,
            node_id=node_id,
            status="queued",
            attempts=0,
            result=None,
            error=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        with self._session_factory() as session:
            session.add(job)
            session.commit()
        return self._to_record(job)

    def enqueue_unique_job(
        self,
        *,
        job_type: str,
        subject_id: str,
        node_id: str | None = None,
    ) -> tuple[JobRecord, bool]:
        now = datetime.now(timezone.utc)
        job = JobORM(
            job_id=uuid4().hex[:12],
            job_type=job_type,
            subject_id=subject_id,
            node_id=node_id,
            status="queued",
            attempts=0,
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as session:
            try:
                session.add(job)
                session.commit()
                return self._to_record(job), True
            except IntegrityError:
                session.rollback()
                existing = (
                    session.query(JobORM)
                    .filter(JobORM.job_type == job_type)
                    .filter(JobORM.subject_id == subject_id)
                    .filter(JobORM.status == "queued")
                    .order_by(JobORM.created_at.asc())
                    .first()
                )
                if existing is None:
                    raise
                return self._to_record(existing), False

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._session_factory() as session:
            job = session.get(JobORM, job_id)
            return self._to_record(job) if job is not None else None

    def list_jobs(
        self,
        *,
        subject_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[JobRecord]:
        with self._session_factory() as session:
            query = session.query(JobORM)
            if subject_id is not None:
                query = query.filter(JobORM.subject_id == subject_id)
            if status is not None:
                query = query.filter(JobORM.status == status)
            jobs = query.order_by(JobORM.created_at.desc()).limit(limit).all()
            return [self._to_record(j) for j in jobs]

    def update_status(self, job_id: str, *, status: str, result: str | None = None, error: str | None = None) -> JobRecord | None:
        with self._session_factory() as session:
            job = session.get(JobORM, job_id)
            if job is None:
                return None
            job.status = status
            job.result = result
            job.error = error
            job.updated_at = datetime.now(timezone.utc)
            session.add(job)
            session.commit()
            return self._to_record(job)

    def claim_next_job(self, *, node_id: str | None = None, include_unassigned: bool = True) -> JobRecord | None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            row = session.execute(
                text(
                    """
                    UPDATE job
                    SET status = 'running',
                        node_id = CASE WHEN node_id IS NULL THEN :node_id ELSE node_id END,
                        attempts = attempts + 1,
                        updated_at = :updated_at
                    WHERE job_id = (
                        SELECT job_id
                        FROM job
                        WHERE status = 'queued'
                          AND (
                            :node_id IS NULL
                            OR node_id = :node_id
                            OR (:include_unassigned = 1 AND node_id IS NULL)
                          )
                        ORDER BY created_at ASC
                        LIMIT 1
                    )
                    RETURNING job_id, job_type, subject_id, node_id, status, attempts, result, error, created_at, updated_at
                    """
                ),
                {
                    "updated_at": now,
                    "node_id": node_id,
                    "include_unassigned": 1 if include_unassigned else 0,
                },
            ).mappings().first()
            if row is None:
                return None
            session.commit()
            return JobRecord(
                job_id=row["job_id"],
                job_type=row["job_type"],
                subject_id=row["subject_id"],
                node_id=row["node_id"],
                status=row["status"],
                attempts=row["attempts"],
                result=row["result"],
                error=row["error"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    @staticmethod
    def _to_record(job: JobORM) -> JobRecord:
        return JobRecord(
            job_id=job.job_id,
            job_type=job.job_type,
            subject_id=job.subject_id,
            node_id=job.node_id,
            status=job.status,
            attempts=job.attempts,
            result=job.result,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
