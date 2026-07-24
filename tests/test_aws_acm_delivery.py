from __future__ import annotations

import json
from pathlib import Path

import pytest

from certman.delivery.aws_acm import deliver_aws_acm_bundle
from certman.providers import AwsCredentials
from certman.services.delivery_service import DeliveryService


ALL_ACM_KEY_TYPES = {
    "RSA_1024",
    "RSA_2048",
    "RSA_3072",
    "RSA_4096",
    "EC_prime256v1",
    "EC_secp384r1",
    "EC_secp521r1",
}
EXPLICIT_ARN = "arn:aws:acm:us-east-1:123456789012:certificate/existing"


class _FakePaginator:
    def __init__(self, pages: list[dict] | None = None):
        self.pages = pages or [{"CertificateSummaryList": []}]
        self.paginate_calls: list[dict] = []

    def paginate(self, **kwargs):
        self.paginate_calls.append(kwargs)
        yield from self.pages


class _FakeAcmClient:
    def __init__(
        self,
        *,
        pages: list[dict] | None = None,
        tags_by_arn: dict[str, dict[str, str]] | None = None,
        certificates_by_arn: dict[str, dict] | None = None,
    ):
        self.paginator = _FakePaginator(pages)
        self.tags_by_arn = tags_by_arn or {}
        self.certificates_by_arn = certificates_by_arn or {}
        self.import_calls: list[dict] = []

    def get_paginator(self, name: str):
        assert name == "list_certificates"
        return self.paginator

    def list_tags_for_certificate(self, CertificateArn: str):
        return {
            "Tags": [
                {"Key": key, "Value": value}
                for key, value in self.tags_by_arn.get(CertificateArn, {}).items()
            ]
        }

    def describe_certificate(self, CertificateArn: str):
        return {"Certificate": self.certificates_by_arn[CertificateArn]}

    def import_certificate(self, **kwargs):
        self.import_calls.append(kwargs)
        return {
            "CertificateArn": kwargs.get(
                "CertificateArn",
                "arn:aws:acm:us-east-1:123456789012:certificate/test-cert",
            )
        }


class _FakeStsClient:
    def __init__(self, account_id: str = "123456789012"):
        self.account_id = account_id
        self.calls = 0

    def get_caller_identity(self):
        self.calls += 1
        return {"Account": self.account_id}


class _FakeSession:
    def __init__(self, client, *, account_id: str = "123456789012"):
        self._client = client
        self.sts_client = _FakeStsClient(account_id)

    def client(self, service_name: str, region_name: str | None = None):
        if service_name == "acm":
            return self._client
        if service_name == "sts":
            return self.sts_client
        raise AssertionError(f"unexpected service: {service_name}")


def _patch_session(
    monkeypatch,
    client: _FakeAcmClient,
    *,
    account_id: str = "123456789012",
) -> _FakeSession:
    session = _FakeSession(client, account_id=account_id)
    monkeypatch.setattr("certman.delivery.aws_acm._create_session", lambda credentials: session)
    return session


def _managed_tags(*, entry_name: str = "site-a", primary_domain: str = "example.com") -> dict[str, str]:
    return {
        "managed-by": "certman",
        "entry-name": entry_name,
        "primary-domain": primary_domain,
    }


def test_deliver_aws_acm_bundle_imports_and_writes_metadata(monkeypatch, tmp_path: Path) -> None:
    client = _FakeAcmClient()
    _patch_session(monkeypatch, client)
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
    assert "CertificateArn" not in client.import_calls[0]
    assert {"Key": "managed-by", "Value": "certman"} in client.import_calls[0]["Tags"]
    assert client.paginator.paginate_calls == [
        {
            "CertificateStatuses": ["ISSUED"],
            "Includes": {"keyTypes": sorted(ALL_ACM_KEY_TYPES)},
        }
    ]


def test_deliver_aws_acm_bundle_finds_and_reuses_ec_prime256v1(monkeypatch, tmp_path: Path) -> None:
    reused_arn = "arn:aws:acm:us-east-1:123456789012:certificate/reused-ec"

    class _EcAwarePaginator(_FakePaginator):
        def paginate(self, **kwargs):
            self.paginate_calls.append(kwargs)
            key_types = kwargs.get("Includes", {}).get("keyTypes", [])
            summaries = []
            if "EC_prime256v1" in key_types:
                summaries.append(
                    {
                        "CertificateArn": reused_arn,
                        "DomainName": "example.com",
                        "Type": "IMPORTED",
                        "KeyAlgorithm": "EC_prime256v1",
                    }
                )
            yield {"CertificateSummaryList": summaries}

    client = _FakeAcmClient(tags_by_arn={reused_arn: _managed_tags()})
    client.paginator = _EcAwarePaginator()
    _patch_session(monkeypatch, client)

    deliver_aws_acm_bundle(
        files={"cert.pem": "CERT", "chain.pem": "CHAIN", "privkey.pem": "KEY"},
        target_dir=tmp_path,
        entry_name="site-a",
        primary_domain="example.com",
        regions=["us-east-1"],
    )

    assert client.import_calls[0]["CertificateArn"] == reused_arn
    assert "Tags" not in client.import_calls[0]
    assert client.paginator.paginate_calls == [
        {
            "CertificateStatuses": ["ISSUED"],
            "Includes": {"keyTypes": sorted(ALL_ACM_KEY_TYPES)},
        }
    ]


def test_deliver_aws_acm_bundle_explicit_arn_updates_in_place(monkeypatch, tmp_path: Path) -> None:
    client = _FakeAcmClient(
        tags_by_arn={EXPLICIT_ARN: _managed_tags()},
        certificates_by_arn={
            EXPLICIT_ARN: {
                "CertificateArn": EXPLICIT_ARN,
                "DomainName": "example.com",
                "Type": "IMPORTED",
            }
        },
    )
    session = _patch_session(monkeypatch, client)

    deliver_aws_acm_bundle(
        files={"cert.pem": "CERT", "chain.pem": "CHAIN", "privkey.pem": "KEY"},
        target_dir=tmp_path,
        entry_name="site-a",
        primary_domain="example.com",
        regions=["us-east-1"],
        certificate_arn={"us-east-1": EXPLICIT_ARN},
    )

    assert session.sts_client.calls == 1
    assert client.paginator.paginate_calls == []
    assert client.import_calls[0]["CertificateArn"] == EXPLICIT_ARN
    assert "Tags" not in client.import_calls[0]


@pytest.mark.parametrize(
    ("certificate_arn", "account_id", "certificate", "tags", "error"),
    [
        (
            "not-an-acm-arn",
            "123456789012",
            {"DomainName": "example.com", "Type": "IMPORTED"},
            _managed_tags(),
            "invalid ACM certificate ARN",
        ),
        (
            "arn:aws:acm:us-west-2:123456789012:certificate/existing",
            "123456789012",
            {"DomainName": "example.com", "Type": "IMPORTED"},
            _managed_tags(),
            "region",
        ),
        (
            EXPLICIT_ARN,
            "999999999999",
            {"DomainName": "example.com", "Type": "IMPORTED"},
            _managed_tags(),
            "account",
        ),
        (
            EXPLICIT_ARN,
            "123456789012",
            {"DomainName": "other.example.com", "Type": "IMPORTED"},
            _managed_tags(),
            "DomainName",
        ),
        (
            EXPLICIT_ARN,
            "123456789012",
            {"DomainName": "example.com", "Type": "AMAZON_ISSUED"},
            _managed_tags(),
            "IMPORTED",
        ),
        (
            EXPLICIT_ARN,
            "123456789012",
            {"DomainName": "example.com", "Type": "IMPORTED"},
            {"managed-by": "someone-else"},
            "tags",
        ),
    ],
)
def test_deliver_aws_acm_bundle_rejects_invalid_explicit_arn(
    monkeypatch,
    tmp_path: Path,
    certificate_arn: str,
    account_id: str,
    certificate: dict,
    tags: dict[str, str],
    error: str,
) -> None:
    client = _FakeAcmClient(
        tags_by_arn={certificate_arn: tags},
        certificates_by_arn={certificate_arn: certificate},
    )
    _patch_session(monkeypatch, client, account_id=account_id)

    with pytest.raises(ValueError, match=error):
        deliver_aws_acm_bundle(
            files={"cert.pem": "CERT", "privkey.pem": "KEY"},
            target_dir=tmp_path,
            entry_name="site-a",
            primary_domain="example.com",
            regions=["us-east-1"],
            certificate_arn={"us-east-1": certificate_arn},
        )

    assert client.import_calls == []


def test_deliver_aws_acm_bundle_fails_closed_for_multiple_matches(monkeypatch, tmp_path: Path) -> None:
    older_arn = "arn:aws:acm:us-east-1:123456789012:certificate/older"
    newer_arn = "arn:aws:acm:us-east-1:123456789012:certificate/newer"
    client = _FakeAcmClient(
        pages=[
            {
                "CertificateSummaryList": [
                    {
                        "CertificateArn": older_arn,
                        "DomainName": "example.com",
                        "Type": "IMPORTED",
                        "CreatedAt": "2026-01-01T00:00:00Z",
                    },
                    {
                        "CertificateArn": newer_arn,
                        "DomainName": "example.com",
                        "Type": "IMPORTED",
                        "CreatedAt": "2026-03-31T00:00:00Z",
                    },
                ]
            }
        ],
        tags_by_arn={
            older_arn: _managed_tags(),
            newer_arn: _managed_tags(),
        },
    )
    _patch_session(monkeypatch, client)

    with pytest.raises(ValueError, match="multiple matching imported certificates"):
        deliver_aws_acm_bundle(
            files={"cert.pem": "CERT", "privkey.pem": "KEY"},
            target_dir=tmp_path,
            entry_name="site-a",
            primary_domain="example.com",
            regions=["us-east-1"],
        )

    assert client.import_calls == []


def test_deliver_aws_acm_bundle_accepts_string_arn_for_single_region(monkeypatch, tmp_path: Path) -> None:
    client = _FakeAcmClient(
        tags_by_arn={EXPLICIT_ARN: _managed_tags()},
        certificates_by_arn={
            EXPLICIT_ARN: {
                "DomainName": "example.com",
                "Type": "IMPORTED",
            }
        },
    )
    _patch_session(monkeypatch, client)

    deliver_aws_acm_bundle(
        files={"cert.pem": "CERT", "privkey.pem": "KEY"},
        target_dir=tmp_path,
        entry_name="site-a",
        primary_domain="example.com",
        regions=["us-east-1"],
        certificate_arn=EXPLICIT_ARN,
    )

    assert client.import_calls[0]["CertificateArn"] == EXPLICIT_ARN


def test_deliver_aws_acm_bundle_rejects_string_arn_for_multiple_regions(monkeypatch, tmp_path: Path) -> None:
    client = _FakeAcmClient()
    _patch_session(monkeypatch, client)

    with pytest.raises(ValueError, match="single region"):
        deliver_aws_acm_bundle(
            files={"cert.pem": "CERT", "privkey.pem": "KEY"},
            target_dir=tmp_path,
            entry_name="site-a",
            primary_domain="example.com",
            regions=["us-east-1", "us-west-2"],
            certificate_arn=EXPLICIT_ARN,
        )


def test_delivery_service_forwards_region_certificate_arn(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    def _capture_delivery(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("certman.services.delivery_service.deliver_aws_acm_bundle", _capture_delivery)

    service = DeliveryService(runtime=None)  # type: ignore[arg-type]
    service._deliver_target(
        target_type="aws-acm",
        target_scope=None,
        files={"cert.pem": "CERT", "privkey.pem": "KEY"},
        target_dir=tmp_path,
        account_id="aws-main",
        options={
            "regions": ["us-east-1"],
            "certificate_arn": {"us-east-1": EXPLICIT_ARN},
        },
        entry_name="site-a",
        primary_domain="example.com",
    )

    assert captured["certificate_arn"] == {"us-east-1": EXPLICIT_ARN}
