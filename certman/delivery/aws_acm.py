from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3

from certman.providers import AwsCredentials, aws_credentials_for_account


@dataclass(frozen=True)
class AwsAcmDeliveryResult:
    certificate_arns: dict[str, str]
    metadata_path: Path


def deliver_aws_acm_bundle(
    *,
    files: dict[str, str],
    target_dir: Path,
    entry_name: str,
    primary_domain: str,
    account_id: str | None = None,
    regions: list[str] | tuple[str, ...] | None = None,
    tags: dict[str, str] | None = None,
) -> list[Path]:
    cert_body = files.get("cert.pem") or files.get("fullchain.pem")
    chain_body = files.get("chain.pem")
    key_body = files.get("privkey.pem")
    if cert_body is None or key_body is None:
        raise ValueError("aws-acm delivery requires cert.pem/fullchain.pem and privkey.pem")

    effective_regions = list(regions or ["us-east-1"])
    effective_tags = {
        "managed-by": "certman",
        "entry-name": entry_name,
        "primary-domain": primary_domain,
    }
    effective_tags.update(tags or {})

    credentials = aws_credentials_for_account(account_id, default_region=effective_regions[0]) if account_id else None
    session = _create_session(credentials)

    arns: dict[str, str] = {}
    for region in effective_regions:
        client = session.client("acm", region_name=region)
        existing_arn = _find_existing_imported_cert_arn(
            client,
            primary_domain=primary_domain,
            required_tags=effective_tags,
        )
        kwargs: dict[str, Any] = {
            "Certificate": cert_body.encode("utf-8"),
            "PrivateKey": key_body.encode("utf-8"),
            "Tags": [{"Key": key, "Value": value} for key, value in effective_tags.items()],
        }
        if chain_body:
            kwargs["CertificateChain"] = chain_body.encode("utf-8")
        if existing_arn:
            kwargs["CertificateArn"] = existing_arn

        response = client.import_certificate(**kwargs)
        arns[region] = response["CertificateArn"]

    target_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = target_dir / "aws-acm-import.json"
    metadata_path.write_text(
        json.dumps(
            {
                "entry_name": entry_name,
                "primary_domain": primary_domain,
                "account_id": account_id,
                "regions": effective_regions,
                "certificate_arns": arns,
                "tags": effective_tags,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return [metadata_path]


def _create_session(credentials: AwsCredentials | None) -> boto3.session.Session:
    if credentials is None:
        return boto3.session.Session()
    return boto3.session.Session(
        aws_access_key_id=credentials.access_key_id,
        aws_secret_access_key=credentials.secret_access_key,
        aws_session_token=credentials.session_token,
        region_name=credentials.region,
    )


def _find_existing_imported_cert_arn(client, *, primary_domain: str, required_tags: dict[str, str]) -> str | None:
    paginator = client.get_paginator("list_certificates")
    candidates: list[dict[str, Any]] = []
    for page in paginator.paginate(CertificateStatuses=["ISSUED"]):
        for summary in page.get("CertificateSummaryList", []):
            if summary.get("DomainName") != primary_domain:
                continue
            if summary.get("Type") != "IMPORTED":
                continue
            arn = summary.get("CertificateArn")
            if not arn:
                continue
            if _certificate_tags_match(client, arn, required_tags):
                candidates.append(summary)

    if not candidates:
        return None

    candidates.sort(key=lambda item: str(item.get("CreatedAt", "")), reverse=True)
    return candidates[0]["CertificateArn"]


def _certificate_tags_match(client, certificate_arn: str, required_tags: dict[str, str]) -> bool:
    response = client.list_tags_for_certificate(CertificateArn=certificate_arn)
    current = {item["Key"]: item["Value"] for item in response.get("Tags", [])}
    return all(current.get(key) == value for key, value in required_tags.items())
