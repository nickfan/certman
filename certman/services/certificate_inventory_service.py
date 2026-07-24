from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from certman.certs import get_cert_status
from certman.config import Runtime
from certman.db.engine import make_engine, make_session_factory
from certman.db.models import Base, CertificateORM
from certman.services.cert_service import resolve_entry_cert_name


class CertificateInventoryService:
    def __init__(self, runtime: Runtime, *, db_path: str | Path):
        self._runtime = runtime
        self._engine = make_engine(db_path)
        Base.metadata.create_all(self._engine)
        self._session_factory = make_session_factory(db_path)

    def sync_entry(self, entry_name: str) -> CertificateORM:
        entry = next((item for item in self._runtime.config.entries if item.name == entry_name), None)
        if entry is None:
            raise ValueError(f"entry not found: {entry_name}")

        cert_name = resolve_entry_cert_name(self._runtime, entry, resolution_mode="latest")
        cert_path = (
            self._runtime.paths.run_dir
            / self._runtime.config.global_.letsencrypt_dir
            / "live"
            / cert_name
            / "cert.pem"
        )
        if not cert_path.exists():
            raise FileNotFoundError(f"certificate not found for entry {entry_name}: {cert_path}")

        now = datetime.now(timezone.utc)
        not_after = get_cert_status(cert_path).not_after
        with self._session_factory() as session:
            certificate = (
                session.query(CertificateORM)
                .filter(CertificateORM.entry_name == entry.name)
                .order_by(CertificateORM.created_at.asc())
                .first()
            )
            if certificate is None:
                certificate = CertificateORM(
                    id=self._certificate_id(entry.name),
                    entry_name=entry.name,
                    primary_domain=entry.primary_domain,
                    status="active",
                    not_after=not_after,
                    created_at=now,
                    updated_at=now,
                )
            else:
                certificate.primary_domain = entry.primary_domain
                certificate.status = "active"
                certificate.not_after = not_after
                certificate.updated_at = now
            session.add(certificate)
            session.commit()
            return certificate

    def reconcile_existing(self) -> list[CertificateORM]:
        reconciled: list[CertificateORM] = []
        for entry in self._runtime.config.entries:
            try:
                reconciled.append(self.sync_entry(entry.name))
            except FileNotFoundError:
                continue
        return reconciled

    @staticmethod
    def _certificate_id(entry_name: str) -> str:
        return f"cert-{sha256(entry_name.encode('utf-8')).hexdigest()[:24]}"
