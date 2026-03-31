from __future__ import annotations

import json
from pathlib import Path

from certman.providers import AwsCredentials
from certman.delivery.aws_acm import deliver_aws_acm_bundle


class _FakePaginator:
    def paginate(self, **kwargs):
        yield {"CertificateSummaryList": []}


class _FakeAcmClient:
    def __init__(self):
        self.import_calls = []

    def get_paginator(self, name: str):
        assert name == "list_certificates"
        return _FakePaginator()

    def list_tags_for_certificate(self, CertificateArn: str):
        return {"Tags": []}

    def import_certificate(self, **kwargs):
        self.import_calls.append(kwargs)
        return {"CertificateArn": "arn:aws:acm:us-east-1:123456789012:certificate/test-cert"}


class _FakeSession:
    def __init__(self, client):
        self._client = client

    def client(self, service_name: str, region_name: str | None = None):
        assert service_name == "acm"
        return self._client


def test_deliver_aws_acm_bundle_imports_and_writes_metadata(monkeypatch, tmp_path: Path) -> None:
    client = _FakeAcmClient()
    monkeypatch.setattr("certman.delivery.aws_acm._create_session", lambda credentials: _FakeSession(client))
    monkeypatch.setattr(
        "certman.delivery.aws_acm.aws_credentials_for_account",
        lambda account_id, default_region="us-east-1": AwsCredentials(
            access_key_id="ak",
            secret_access_key="sk",
            region=default_region,
            session_token=None,
        ),
    )

    written = deliver_aws_acm_bundle(
        files={
            "cert.pem": "CERT",
            "chain.pem": "CHAIN",
            "privkey.pem": "KEY",
        },
        target_dir=tmp_path,
        entry_name="site-a",
        primary_domain="example.com",
        account_id="aws-main",
        regions=["us-east-1"],
        tags={"env": "dev"},
    )

    assert len(written) == 1
    payload = json.loads((tmp_path / "aws-acm-import.json").read_text(encoding="utf-8"))
    assert payload["entry_name"] == "site-a"
    assert payload["regions"] == ["us-east-1"]
    assert payload["certificate_arns"]["us-east-1"].endswith("test-cert")
    assert client.import_calls[0]["Certificate"] == b"CERT"
    assert client.import_calls[0]["PrivateKey"] == b"KEY"


def test_deliver_aws_acm_bundle_reuses_matching_arn(monkeypatch, tmp_path: Path) -> None:
    class _ReusedPaginator:
        def paginate(self, **kwargs):
            yield {
                "CertificateSummaryList": [
                    {
                        "CertificateArn": "arn:aws:acm:us-east-1:123456789012:certificate/reused",
                        "DomainName": "example.com",
                        "Type": "IMPORTED",
                        "CreatedAt": "2026-03-31T00:00:00Z",
                    }
                ]
            }

    class _ReusedClient(_FakeAcmClient):
        def get_paginator(self, name: str):
            assert name == "list_certificates"
            return _ReusedPaginator()

        def list_tags_for_certificate(self, CertificateArn: str):
            return {
                "Tags": [
                    {"Key": "managed-by", "Value": "certman"},
                    {"Key": "entry-name", "Value": "site-a"},
                    {"Key": "primary-domain", "Value": "example.com"},
                ]
            }

    client = _ReusedClient()
    monkeypatch.setattr("certman.delivery.aws_acm._create_session", lambda credentials: _FakeSession(client))
    monkeypatch.setattr(
        "certman.delivery.aws_acm.aws_credentials_for_account",
        lambda account_id, default_region="us-east-1": AwsCredentials(
            access_key_id="ak",
            secret_access_key="sk",
            region=default_region,
            session_token=None,
        ),
    )

    deliver_aws_acm_bundle(
        files={"cert.pem": "CERT", "chain.pem": "CHAIN", "privkey.pem": "KEY"},
        target_dir=tmp_path,
        entry_name="site-a",
        primary_domain="example.com",
        regions=["us-east-1"],
    )

    assert client.import_calls[0]["CertificateArn"].endswith("reused")
