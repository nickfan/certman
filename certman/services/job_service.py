from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
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
        self._migrate_legacy_job_uniqueness()
        self._session_factory = make_session_factory(self._db_path)

    def _migrate_legacy_job_uniqueness(self) -> None:
        # SQLite cannot drop a table-level UNIQUE constraint without rebuilding the table.
        with sqlite3.connect(self._db_path, timeout=30) as db:
            db.execute("BEGIN IMMEDIATE")
            schema_row = db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='job'"
            ).fetchone()
            schema = schema_row[0] if schema_row else ""
            legacy_constraint = "CONSTRAINT uq_job_type_subject_status UNIQUE (job_type, subject_id, status)"
            if legacy_constraint in schema:
                db.execute("DROP INDEX IF EXISTS ux_job_type_subject_queued")
                db.execute("CREATE TABLE job_new (job_id VARCHAR(64) NOT NULL PRIMARY KEY, job_type VARCHAR(64) NOT NULL, subject_id VARCHAR(128) NOT NULL, target_type VARCHAR(64) NOT NULL, target_scope VARCHAR(128), node_id VARCHAR(128), status VARCHAR(32) NOT NULL, attempts INTEGER NOT NULL, result TEXT, error TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)")
                columns = "job_id, job_type, subject_id, target_type, target_scope, node_id, status, attempts, result, error, created_at, updated_at"
                db.execute(f"INSERT INTO job_new ({columns}) SELECT {columns} FROM job")
                db.execute("DROP TABLE job")
                db.execute("ALTER TABLE job_new RENAME TO job")
                db.execute("CREATE INDEX IF NOT EXISTS ix_job_status ON job (status)")
            db.execute("DROP INDEX IF EXISTS ux_job_type_subject_status")
            db.execute("UPDATE job SET status = 'cancelled', error = COALESCE(error, 'normalized from abandoned recovery state') WHERE status IN ('stale', 'abandoned')")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_job_type_subject_queued ON job (job_type, subject_id) WHERE status = 'queued'")
            db.commit()

    def create_job(
        self,
        *,
        job_type: str,
        subject_id: str,
        node_id: str | None = None,
        target_type: str = "generic",
        target_scope: str | None = None,
    ) -> JobRecord:
        job = JobORM(
            job_id=uuid4().hex[:12],
            job_type=job_type,
            subject_id=subject_id,
            target_type=target_type,
            target_scope=target_scope,
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
        target_type: str = "generic",
        target_scope: str | None = None,
    ) -> tuple[JobRecord, bool]:
        now = datetime.now(timezone.utc)
        job = JobORM(
            job_id=uuid4().hex[:12],
            job_type=job_type,
            subject_id=subject_id,
            target_type=target_type,
            target_scope=target_scope,
            node_id=node_id,
            status="queued",
            attempts=0,
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as session:
            existing = (
                session.query(JobORM)
                .filter(JobORM.job_type == job_type, JobORM.subject_id == subject_id)
                .filter(JobORM.status.in_(("queued", "running")))
                .order_by(JobORM.created_at.asc())
                .first()
            )
            if existing is not None:
                return self._to_record(existing), False
            try:
                session.add(job)
                session.commit()
                return self._to_record(job), True
            except IntegrityError:
                session.rollback()
                existing = (
                    session.query(JobORM)
                    .filter(JobORM.job_type == job_type, JobORM.subject_id == subject_id)
                    .filter(JobORM.status == "queued")
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
        target_scope: str | None = None,
        limit: int = 50,
    ) -> list[JobRecord]:
        with self._session_factory() as session:
            query = session.query(JobORM)
            if subject_id is not None:
                query = query.filter(JobORM.subject_id == subject_id)
            if status is not None:
                query = query.filter(JobORM.status == status)
            if target_scope is not None:
                query = query.filter(JobORM.target_scope == target_scope)
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

    def claim_next_job(
        self,
        *,
        node_id: str | None = None,
        include_unassigned: bool = True,
        target_scope: str | None = None,
    ) -> JobRecord | None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            # ponytail: a two-hour lease assumes certificate jobs finish sooner; add heartbeats if longer jobs become normal.
            session.query(JobORM).filter(
                JobORM.status == "running", JobORM.updated_at < now - timedelta(hours=2)
            ).update({JobORM.status: "failed", JobORM.error: "worker lease expired", JobORM.updated_at: now})
            session.commit()
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
                                                    AND (:target_scope IS NULL OR target_scope = :target_scope)
                          AND (
                            :node_id IS NULL
                            OR node_id = :node_id
                            OR (:include_unassigned = 1 AND node_id IS NULL)
                          )
                        ORDER BY created_at ASC
                        LIMIT 1
                    )
                    RETURNING job_id, job_type, subject_id, target_type, target_scope, node_id, status, attempts, result, error, created_at, updated_at
                    """
                ),
                {
                    "updated_at": now,
                    "node_id": node_id,
                    "target_scope": target_scope,
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
                target_type=row["target_type"],
                target_scope=row["target_scope"],
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
            target_type=job.target_type,
            target_scope=job.target_scope,
            node_id=job.node_id,
            status=job.status,
            attempts=job.attempts,
            result=job.result,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
