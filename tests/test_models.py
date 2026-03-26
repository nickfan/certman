from __future__ import annotations

from datetime import datetime

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
    assert model.node_id is None
    assert model.result is None
    assert model.error is None
    assert isinstance(model.created_at, datetime)
    assert isinstance(model.updated_at, datetime)


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


def test_certificate_record_has_optional_timestamps() -> None:
    model = CertificateRecord(
        certificate_id="cert-2",
        entry_name="site-b",
        primary_domain="example.org",
        issuer="letsencrypt",
        status="active",
    )
    assert model.not_after is None
    assert isinstance(model.created_at, datetime)
    assert isinstance(model.updated_at, datetime)


def test_node_identity_record_defaults() -> None:
    model = NodeIdentityRecord(node_id="node-b", node_type="agent", public_key_id="pub-2")
    assert model.status == "active"
    assert model.last_seen is None
    assert isinstance(model.created_at, datetime)
    assert isinstance(model.updated_at, datetime)
