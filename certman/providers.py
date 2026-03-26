from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from certman.config import EntryConfig, normalize_account_id


@dataclass(frozen=True)
class AliyunCredentials:
    access_key_id: str
    access_key_secret: str


@dataclass(frozen=True)
class CloudflareCredentials:
    api_token: str


@dataclass(frozen=True)
class Route53Credentials:
    access_key_id: str
    secret_access_key: str
    region: str


def _resolve_value(value: str) -> str:
    value = value.strip()
    if value.startswith("${") and value.endswith("}"):
        key = value[2:-1].strip()
        resolved = os.getenv(key)
        if not resolved:
            raise ValueError(f"missing env var for reference: {key}")
        return resolved
    return value


# ---------------------------------------------------------------------------
# Aliyun
# ---------------------------------------------------------------------------

def aliyun_credentials_for_entry(entry: EntryConfig) -> AliyunCredentials:
    # 1) explicit credentials
    creds = entry.credentials
    if creds.access_key_id and creds.access_key_secret:
        return AliyunCredentials(
            access_key_id=_resolve_value(creds.access_key_id),
            access_key_secret=_resolve_value(creds.access_key_secret),
        )

    # 2) account_id from env convention
    if not entry.account_id:
        raise ValueError("aliyun entry missing account_id or credentials")

    account = normalize_account_id(entry.account_id)
    ak = os.getenv(f"CERTMAN_ALIYUN_{account}_ACCESS_KEY_ID")
    sk = os.getenv(f"CERTMAN_ALIYUN_{account}_ACCESS_KEY_SECRET")
    if not ak or not sk:
        raise ValueError(f"missing aliyun env keys for account_id={entry.account_id}")

    return AliyunCredentials(access_key_id=ak, access_key_secret=sk)


def write_aliyun_credentials_ini(path: Path, creds: AliyunCredentials) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "dns_aliyun_access_key = "
        + creds.access_key_id
        + "\n"
        + "dns_aliyun_access_key_secret = "
        + creds.access_key_secret
        + "\n"
    )
    path.write_text(content, encoding="utf-8")

    try:
        os.chmod(path, 0o600)
    except OSError:
        # On Windows, chmod has limited effect
        pass


# ---------------------------------------------------------------------------
# Cloudflare
# ---------------------------------------------------------------------------

def cloudflare_credentials_for_entry(entry: EntryConfig) -> CloudflareCredentials:
    # 1) explicit credentials
    creds = entry.credentials
    if creds.api_token:
        return CloudflareCredentials(api_token=_resolve_value(creds.api_token))

    # 2) account_id from env convention
    if not entry.account_id:
        raise ValueError("cloudflare entry missing account_id or credentials.api_token")

    account = normalize_account_id(entry.account_id)
    token = os.getenv(f"CERTMAN_CLOUDFLARE_{account}_API_TOKEN")
    if not token:
        raise ValueError(
            f"missing cloudflare env key for account_id={entry.account_id}"
        )

    return CloudflareCredentials(api_token=token)


def write_cloudflare_credentials_ini(path: Path, creds: CloudflareCredentials) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "dns_cloudflare_api_token = " + creds.api_token + "\n"
    path.write_text(content, encoding="utf-8")

    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Route 53 (AWS)
# ---------------------------------------------------------------------------

def route53_credentials_for_entry(entry: EntryConfig) -> Route53Credentials:
    account = normalize_account_id(entry.account_id) if entry.account_id else None

    # 1) explicit credentials
    creds = entry.credentials
    if creds.access_key_id and creds.access_key_secret:
        return Route53Credentials(
            access_key_id=_resolve_value(creds.access_key_id),
            secret_access_key=_resolve_value(creds.access_key_secret),
            region=_resolve_value(
                os.getenv(f"CERTMAN_AWS_{account}_REGION", "us-east-1")
                if account
                else "us-east-1"
            ),
        )

    # 2) account_id from env convention
    if not entry.account_id:
        raise ValueError("route53 entry missing account_id or credentials")

    ak = os.getenv(f"CERTMAN_AWS_{account}_ACCESS_KEY_ID")
    sk = os.getenv(f"CERTMAN_AWS_{account}_SECRET_ACCESS_KEY")
    region = os.getenv(f"CERTMAN_AWS_{account}_REGION", "us-east-1")
    if not ak or not sk:
        raise ValueError(
            f"missing route53 env keys for account_id={entry.account_id}"
        )

    return Route53Credentials(access_key_id=ak, secret_access_key=sk, region=region)


def write_route53_credentials_ini(path: Path, creds: Route53Credentials) -> None:
    """Write AWS credentials ini used by certbot-dns-route53 via boto3 profile."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[default]\n"
        "aws_access_key_id = " + creds.access_key_id + "\n"
        "aws_secret_access_key = " + creds.secret_access_key + "\n"
        "region = " + creds.region + "\n"
    )
    path.write_text(content, encoding="utf-8")

    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
