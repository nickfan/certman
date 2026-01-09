from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from certman.config import EntryConfig


@dataclass(frozen=True)
class AliyunCredentials:
    access_key_id: str
    access_key_secret: str


def _resolve_value(value: str) -> str:
    value = value.strip()
    if value.startswith("${") and value.endswith("}"):
        key = value[2:-1].strip()
        resolved = os.getenv(key)
        if not resolved:
            raise ValueError(f"missing env var for reference: {key}")
        return resolved
    return value


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

    ak = os.getenv(f"CERTMAN_ALIYUN_{entry.account_id}_ACCESS_KEY_ID")
    sk = os.getenv(f"CERTMAN_ALIYUN_{entry.account_id}_ACCESS_KEY_SECRET")
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
