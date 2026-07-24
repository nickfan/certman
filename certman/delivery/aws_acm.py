from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3

from certman.providers import AwsCredentials, aws_credentials_for_account


_ALL_ACM_KEY_TYPES = [
    "EC_prime256v1",
    "EC_secp384r1",
    "EC_secp521r1",
    "RSA_1024",
    "RSA_2048",
    "RSA_3072",
    "RSA_4096",
]


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
    certificate_arn: str | dict[str, str] | None = None,
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
    explicit_arns = _normalize_explicit_certificate_arns(
        certificate_arn,
        regions=effective_regions,
    )

    credentials = (
        aws_credentials_for_account(account_id, default_region=effective_regions[0])
        if account_id
        else None
    )
    session = _create_session(credentials)
    active_account_id = (
        _get_active_account_id(session, region=effective_regions[0])
        if explicit_arns
        else ""
    )

    arns: dict[str, str] = {}
    for region in effective_regions:
        client = session.client("acm", region_name=region)
        existing_arn = explicit_arns.get(region)
        if existing_arn:
            _validate_explicit_imported_certificate(
                client,
                certificate_arn=existing_arn,
                expected_account_id=active_account_id,
                expected_region=region,
                primary_domain=primary_domain,
                required_tags=effective_tags,
            )
        else:
            existing_arn = _find_existing_imported_cert_arn(
                client,
                primary_domain=primary_domain,
                required_tags=effective_tags,
            )
        kwargs: dict[str, Any] = {
            "Certificate": cert_body.encode("utf-8"),
            "PrivateKey": key_body.encode("utf-8"),
        }
        if chain_body:
            kwargs["CertificateChain"] = chain_body.encode("utf-8")
        if existing_arn:
            kwargs["CertificateArn"] = existing_arn
        else:
            kwargs["Tags"] = [{"Key": key, "Value": value} for key, value in effective_tags.items()]

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
    candidates: set[str] = set()
    for page in paginator.paginate(
        CertificateStatuses=["ISSUED"],
        Includes={"keyTypes": _ALL_ACM_KEY_TYPES},
    ):
        for summary in page.get("CertificateSummaryList", []):
            if summary.get("DomainName") != primary_domain:
                continue
            if summary.get("Type") != "IMPORTED":
                continue
            arn = summary.get("CertificateArn")
            if not arn:
                continue
            if _certificate_tags_match(client, arn, required_tags):
                candidates.add(arn)

    if not candidates:
        return None
    if len(candidates) > 1:
        candidate_text = ", ".join(sorted(candidates))
        raise ValueError(
            "multiple matching imported certificates found for "
            f"DomainName={primary_domain}: {candidate_text}; "
            "configure delivery_targets.options.certificate_arn explicitly"
        )
    return next(iter(candidates))


def _certificate_tags_match(client, certificate_arn: str, required_tags: dict[str, str]) -> bool:
    response = client.list_tags_for_certificate(CertificateArn=certificate_arn)
    current = {item["Key"]: item["Value"] for item in response.get("Tags", [])}
    return all(current.get(key) == value for key, value in required_tags.items())


def _normalize_explicit_certificate_arns(
    certificate_arn: str | dict[str, str] | None,
    *,
    regions: list[str],
) -> dict[str, str]:
    if certificate_arn is None:
        return {}
    if isinstance(certificate_arn, str):
        normalized = certificate_arn.strip()
        if not normalized:
            return {}
        if len(regions) != 1:
            raise ValueError(
                "delivery_targets.options.certificate_arn may be a string only for a single region"
            )
        arn_region, _ = _parse_acm_certificate_arn(normalized)
        if arn_region != regions[0]:
            raise ValueError(
                f"explicit ACM certificate ARN region={arn_region} "
                f"does not match target region={regions[0]}"
            )
        return {regions[0]: normalized}
    if not isinstance(certificate_arn, dict):
        raise ValueError(
            "delivery_targets.options.certificate_arn must be an ARN string or a region-to-ARN mapping"
        )

    explicit_arns: dict[str, str] = {}
    for raw_region, raw_arn in certificate_arn.items():
        region = str(raw_region).strip()
        if region not in regions:
            raise ValueError(
                f"certificate_arn configured for region={region}, which is not present in regions"
            )
        if not isinstance(raw_arn, str) or not raw_arn.strip():
            raise ValueError(f"certificate_arn for region={region} must be a non-empty string")
        normalized_arn = raw_arn.strip()
        arn_region, _ = _parse_acm_certificate_arn(normalized_arn)
        if arn_region != region:
            raise ValueError(
                f"explicit ACM certificate ARN region={arn_region} "
                f"does not match configured region={region}"
            )
        explicit_arns[region] = normalized_arn
    return explicit_arns


def _get_active_account_id(session, *, region: str) -> str:
    response = session.client("sts", region_name=region).get_caller_identity()
    account_id = str(response.get("Account", "")).strip()
    if not account_id:
        raise ValueError("unable to determine active AWS account for explicit ACM certificate ARN")
    return account_id


def _validate_explicit_imported_certificate(
    client,
    *,
    certificate_arn: str,
    expected_account_id: str,
    expected_region: str,
    primary_domain: str,
    required_tags: dict[str, str],
) -> None:
    arn_region, arn_account_id = _parse_acm_certificate_arn(certificate_arn)
    if arn_region != expected_region:
        raise ValueError(
            f"explicit ACM certificate ARN region={arn_region} does not match target region={expected_region}"
        )
    if arn_account_id != expected_account_id:
        raise ValueError(
            "explicit ACM certificate ARN account does not match the active AWS account"
        )

    certificate = client.describe_certificate(CertificateArn=certificate_arn).get("Certificate", {})
    if certificate.get("DomainName") != primary_domain:
        raise ValueError(
            "explicit ACM certificate ARN DomainName does not match "
            f"primary_domain={primary_domain}"
        )
    if certificate.get("Type") != "IMPORTED":
        raise ValueError("explicit ACM certificate ARN must reference Type=IMPORTED")
    if not _certificate_tags_match(client, certificate_arn, required_tags):
        raise ValueError("explicit ACM certificate ARN does not match the required tags")


def _parse_acm_certificate_arn(certificate_arn: str) -> tuple[str, str]:
    parts = certificate_arn.split(":", 5)
    if len(parts) != 6:
        raise ValueError("invalid ACM certificate ARN")
    arn_prefix, partition, service, region, account_id, resource = parts
    if (
        arn_prefix != "arn"
        or not partition
        or service != "acm"
        or not region
        or len(account_id) != 12
        or not account_id.isdigit()
        or not resource.startswith("certificate/")
        or resource == "certificate/"
    ):
        raise ValueError("invalid ACM certificate ARN")
    return region, account_id
