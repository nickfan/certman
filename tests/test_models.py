from __future__ import annotations

from certman.models.certificate import CertificateRecord
from certman.models.job import JobRecord
from certman.models.node import NodeIdentityRecord


def test_certificate_record_serializes() -> None:
    model = CertificateRecord(
        certificate_id="cert-1",
        entry_name="site-a",
        primary_domain="example.com",
        domains=["example.com", "www.example.com"],
        issuer="letsencrypt",
        status="active",
    )

    payload = model.model_dump()

    assert payload["certificate_id"] == "cert-1"
    assert payload["status"] == "active"


def test_job_record_defaults() -> None:
    model = JobRecord(job_id="job-1", job_type="renew", subject_id="site-a")

    assert model.status == "queued"
    assert model.attempts == 0


def test_node_identity_record_serializes() -> None:
    model = NodeIdentityRecord(
        node_id="node-a",
        node_type="agent",
        public_key_id="pub-1",
        allowed_targets=["filesystem"],
        allowed_certificates=["site-a"],
    )

    payload = model.model_dump()

    assert payload["node_id"] == "node-a"
    assert payload["allowed_targets"] == ["filesystem"]
