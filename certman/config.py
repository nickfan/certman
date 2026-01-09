from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import os

import yaml

import tomllib

_toml_loads = tomllib.loads

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# imported lazily in create_runtime to avoid cycles


class GlobalConfig(BaseModel):
    data_dir: str = "data"
    conf_dir: str = "conf"
    run_dir: str = "run"
    log_dir: str = "log"
    output_dir: str = "output"
    letsencrypt_dir: str = "letsencrypt"

    acme_server: str = "staging"  # staging|prod
    email: str = "admin@example.com"


class CredentialsConfig(BaseModel):
    # Optional raw creds (portable mode)
    access_key_id: str | None = None
    access_key_secret: str | None = None
    api_token: str | None = None


class EntryConfig(BaseModel):
    name: str
    description: str = ""
    primary_domain: str
    secondary_domains: list[str] = Field(default_factory=list)
    wildcard: bool = True

    dns_provider: str  # cloudflare|route53|aliyun

    # Optional: reference an account in .env (ops mode)
    account_id: str | None = None

    # Optional: embed credentials directly or via ${ENV_VAR}
    credentials: CredentialsConfig = Field(default_factory=CredentialsConfig)


class AppConfig(BaseModel):
    global_: GlobalConfig = Field(alias="global")
    entries: list[EntryConfig] = Field(default_factory=list)

    def validate_required_secrets(self, env: dict[str, str]) -> None:
        missing: list[str] = []
        for entry in self.entries:
            missing.extend(_required_env_keys(entry, env))

        if missing:
            missing_sorted = "\n".join(sorted(set(missing)))
            raise ValueError(f"Missing required env keys:\n{missing_sorted}")


class GlobalOnlyConfig(BaseModel):
    global_: GlobalConfig = Field(alias="global")
    scan_items_glob: str = "item_*.toml"


def _is_env_ref(value: str) -> bool:
    return value.startswith("${") and value.endswith("}") and len(value) > 3


def _env_ref_key(value: str) -> str:
    return value[2:-1].strip()


def _required_env_keys(entry: EntryConfig, env: dict[str, str]) -> list[str]:
    """Return required env keys for an entry.

    Rules:
    - if credentials are provided (raw or ${ENV}), prefer them
    - otherwise, if account_id is provided, require provider+account_id keys
    """

    provider = entry.dns_provider.lower()

    missing: list[str] = []

    # 1) explicit credentials (portable mode): only validate env refs
    creds = entry.credentials
    for value in [creds.access_key_id, creds.access_key_secret, creds.api_token]:
        if not value:
            continue
        if _is_env_ref(value):
            k = _env_ref_key(value)
            if not env.get(k):
                missing.append(k)

    has_any_plain_credential = any(
        [
            creds.access_key_id and not _is_env_ref(creds.access_key_id),
            creds.access_key_secret and not _is_env_ref(creds.access_key_secret),
            creds.api_token and not _is_env_ref(creds.api_token),
        ]
    )

    if missing or has_any_plain_credential:
        # already validated env refs, or provided raw secrets
        return missing

    # 2) ops mode: require account_id based variables
    account = entry.account_id
    if not account:
        # No account_id and no portable credentials: treat as non-actionable.
        # This keeps template/placeholder entries from breaking config-validate.
        return []

    required: list[str]
    if provider == "cloudflare":
        required = [f"CERTMAN_CLOUDFLARE_{account}_API_TOKEN"]
    elif provider == "route53":
        required = [
            f"CERTMAN_AWS_{account}_ACCESS_KEY_ID",
            f"CERTMAN_AWS_{account}_SECRET_ACCESS_KEY",
            f"CERTMAN_AWS_{account}_REGION",
        ]
    elif provider == "aliyun":
        required = [
            f"CERTMAN_ALIYUN_{account}_ACCESS_KEY_ID",
            f"CERTMAN_ALIYUN_{account}_ACCESS_KEY_SECRET",
        ]
    else:
        raise ValueError(f"unsupported dns_provider: {entry.dns_provider}")

    return [k for k in required if not env.get(k)]


@dataclass(frozen=True)
class Paths:
    data_dir: Path
    conf_dir: Path
    run_dir: Path
    log_dir: Path
    output_dir: Path


@dataclass(frozen=True)
class Runtime:
    paths: Paths
    config: AppConfig
    env: dict[str, str]


def create_runtime(data_dir: str, config_file: str | None) -> Runtime:
    base = Path(data_dir)
    conf_dir = base / "conf"
    run_dir = base / "run"
    log_dir = base / "log"
    output_dir = base / "output"

    # Load dotenv from data/conf/.env by default (optional)
    dotenv_path = conf_dir / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=False)

    # Default layout:
    # - data/conf/config.toml: global config + scan pattern
    # - data/conf/item_*.toml: portable entries
    config_filename = config_file or os.getenv("CERTMAN_CONFIG_FILE") or "config.toml"
    cfg_path = conf_dir / config_filename

    # Lazy import to avoid circular imports
    from certman.config_merge import load_merged_config

    config = load_merged_config(cfg_path)

    # allow overriding data_dir in config (mostly for docker /data)
    if config.global_.data_dir and config.global_.data_dir != data_dir:
        base = Path(config.global_.data_dir)
        conf_dir = base / config.global_.conf_dir
        run_dir = base / config.global_.run_dir
        log_dir = base / config.global_.log_dir
        output_dir = base / config.global_.output_dir

    paths = Paths(
        data_dir=base,
        conf_dir=conf_dir,
        run_dir=run_dir,
        log_dir=log_dir,
        output_dir=output_dir,
    )

    env = dict(os.environ)

    return Runtime(paths=paths, config=config, env=env)


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")

    suffix = path.suffix.lower()
    raw: dict
    if suffix == ".toml":
        raw = _toml_loads(path.read_text(encoding="utf-8"))
    elif suffix in {".yaml", ".yml"}:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"unsupported config format: {suffix}")

    return AppConfig.model_validate(raw)
