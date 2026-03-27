from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import os
import tomllib

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

_toml_loads = tomllib.loads


class GlobalConfig(BaseModel):
    data_dir: str = "data"
    conf_dir: str = "conf"
    run_dir: str = "run"
    log_dir: str = "log"
    output_dir: str = "output"
    letsencrypt_dir: str = "letsencrypt"

    acme_server: str = "staging"  # staging|prod
    email: str = "admin@example.com"
    token: str | None = None


class ControlPlaneConfig(BaseModel):
    endpoint: str
    poll_interval_seconds: int = 30


class ServerConfig(BaseModel):
    db_path: str = "data/run/certman.db"
    listen_host: str = "0.0.0.0"
    listen_port: int = 8000
    signing_key_path: str | None = None  # Ed25519 private key; required in Phase 4
    token_auth_enabled: bool = False


class SchedulerConfig(BaseModel):
    enabled: bool = False
    mode: Literal["loop", "cron"] = "loop"
    scan_interval_seconds: int = 300
    cron_expr: str = "0 * * * *"
    cron_poll_seconds: int = 15
    renew_before_days: int = 30


class NodeIdentityConfig(BaseModel):
    node_id: str
    private_key_path: str
    public_key_path: str | None = None
    certificate_store_path: str | None = None


class HookConfig(BaseModel):
    name: str
    event: str
    command: str
    shell: bool = True


class CredentialsConfig(BaseModel):
    # Optional raw creds (portable mode)
    access_key_id: str | None = None
    access_key_secret: str | None = None
    api_token: str | None = None


class EntryConfig(BaseModel):
    name: str
    description: str = ""
    primary_domain: str
    cert_name: str | None = None
    secondary_domains: list[str] = Field(default_factory=list)
    wildcard: bool = True

    dns_provider: str  # cloudflare|route53|aliyun

    # Optional: reference an account in .env (ops mode)
    account_id: str | None = None

    # Optional: embed credentials directly or via ${ENV_VAR}
    credentials: CredentialsConfig = Field(default_factory=CredentialsConfig)
    token: str | None = None


class AppConfig(BaseModel):
    run_mode: Literal["local", "agent", "server"] = "local"
    global_: GlobalConfig = Field(alias="global")
    entries: list[EntryConfig] = Field(default_factory=list)
    control_plane: ControlPlaneConfig | None = None
    node_identity: NodeIdentityConfig | None = None
    hooks: list[HookConfig] = Field(default_factory=list)
    server: ServerConfig | None = None
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)

    @model_validator(mode="after")
    def _validate_run_mode(self):
        if self.run_mode == "agent":
            if self.control_plane is None or not self.control_plane.endpoint:
                raise ValueError("agent mode requires control_plane.endpoint")
            if self.node_identity is None or not self.node_identity.private_key_path:
                raise ValueError("agent mode requires node_identity.private_key_path")
        elif self.run_mode == "server":
            if self.server is None:
                raise ValueError("server mode requires [server] configuration block")
        return self

    def validate_required_secrets(
        self,
        env: dict[str, str],
        *,
        entry_names: list[str] | None = None,
        validate_all: bool = False,
    ) -> None:
        if validate_all and entry_names:
            raise ValueError("cannot combine validate_all with entry_names")

        if not validate_all and not entry_names:
            raise ValueError("config validation requires explicit entry_names or validate_all=True")

        selected_entries = self.entries
        if entry_names:
            wanted_names = set(entry_names)
            selected_entries = [entry for entry in self.entries if entry.name in wanted_names]

            found_names = {entry.name for entry in selected_entries}
            missing_names = sorted(wanted_names - found_names)
            if missing_names:
                missing_text = ", ".join(missing_names)
                raise ValueError(f"Unknown entry names: {missing_text}")

        missing: list[str] = []
        for entry in selected_entries:
            missing.extend(_required_env_keys(entry, env))

        if missing:
            missing_sorted = "\n".join(sorted(set(missing)))
            raise ValueError(f"Missing required env keys:\n{missing_sorted}")


class GlobalOnlyConfig(BaseModel):
    run_mode: Literal["local", "agent", "server"] = "local"
    global_: GlobalConfig = Field(alias="global")
    scan_items_glob: str = "item_*.toml"
    control_plane: ControlPlaneConfig | None = None
    node_identity: NodeIdentityConfig | None = None
    hooks: list[HookConfig] = Field(default_factory=list)
    server: ServerConfig | None = None
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)


def _parse_bool_env(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean env value: {value}")


def _scheduler_env_fallback(
    config: AppConfig,
    env: dict[str, str],
    *,
    explicit_scheduler_fields: set[str] | None = None,
) -> None:
    defaults = SchedulerConfig()
    scheduler = config.scheduler
    if explicit_scheduler_fields is None:
        explicit_fields = set(getattr(scheduler, "model_fields_set", set()))
    else:
        explicit_fields = set(explicit_scheduler_fields)

    def _can_fallback(field_name: str, current_value, default_value) -> bool:
        return field_name not in explicit_fields and current_value == default_value

    raw_enabled = env.get("CERTMAN_SCHEDULER_ENABLED")
    if raw_enabled is not None and _can_fallback("enabled", scheduler.enabled, defaults.enabled):
        scheduler.enabled = _parse_bool_env(raw_enabled)

    raw_mode = env.get("CERTMAN_SCHEDULER_MODE")
    if raw_mode and _can_fallback("mode", scheduler.mode, defaults.mode):
        mode = raw_mode.strip().lower()
        if mode in {"loop", "cron"}:
            scheduler.mode = mode
        else:
            raise ValueError("CERTMAN_SCHEDULER_MODE must be loop or cron")

    raw_scan_interval = env.get("CERTMAN_SCHEDULER_SCAN_INTERVAL_SECONDS")
    if raw_scan_interval is not None and _can_fallback(
        "scan_interval_seconds", scheduler.scan_interval_seconds, defaults.scan_interval_seconds
    ):
        scheduler.scan_interval_seconds = int(raw_scan_interval)

    raw_cron_expr = env.get("CERTMAN_SCHEDULER_CRON_EXPR")
    if raw_cron_expr and _can_fallback("cron_expr", scheduler.cron_expr, defaults.cron_expr):
        scheduler.cron_expr = raw_cron_expr

    raw_cron_poll = env.get("CERTMAN_SCHEDULER_CRON_POLL_SECONDS")
    if raw_cron_poll is not None and _can_fallback(
        "cron_poll_seconds", scheduler.cron_poll_seconds, defaults.cron_poll_seconds
    ):
        scheduler.cron_poll_seconds = int(raw_cron_poll)

    raw_renew_before = env.get("CERTMAN_SCHEDULER_RENEW_BEFORE_DAYS")
    if raw_renew_before is not None and _can_fallback(
        "renew_before_days", scheduler.renew_before_days, defaults.renew_before_days
    ):
        scheduler.renew_before_days = int(raw_renew_before)


def _is_env_ref(value: str) -> bool:
    return value.startswith("${") and value.endswith("}") and len(value) > 3


def entry_domains(entry: EntryConfig) -> list[str]:
    """Return deduplicated domain list for an entry, including wildcard if enabled."""
    domains = [entry.primary_domain, *entry.secondary_domains]
    if entry.wildcard:
        domains.append(f"*.{entry.primary_domain}")

    seen: set[str] = set()
    unique: list[str] = []
    for domain in domains:
        if domain in seen:
            continue
        seen.add(domain)
        unique.append(domain)
    return unique


def _env_ref_key(value: str) -> str:
    return value[2:-1].strip()


def normalize_account_id(account_id: str) -> str:
    return account_id.strip().replace("-", "_").upper()


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
    account = normalize_account_id(entry.account_id) if entry.account_id else None
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


def resolve_runtime_path(runtime: Runtime, configured_path: str | Path) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    return runtime.paths.data_dir.parent / path


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
    from certman.config_merge import load_config_dict, load_merged_config

    config = load_merged_config(cfg_path)
    env = dict(os.environ)
    raw_cfg = load_config_dict(cfg_path)
    raw_scheduler = raw_cfg.get("scheduler", {}) if isinstance(raw_cfg, dict) else {}
    explicit_scheduler_fields = set(raw_scheduler.keys()) if isinstance(raw_scheduler, dict) else set()
    _scheduler_env_fallback(config, env, explicit_scheduler_fields=explicit_scheduler_fields)

    # allow overriding data_dir in config (mostly for docker /data)
    if config.global_.data_dir:
        configured_base = Path(config.global_.data_dir)
        if configured_base.is_absolute() and configured_base != base:
            base = configured_base
            conf_dir = base / config.global_.conf_dir
            run_dir = base / config.global_.run_dir
            log_dir = base / config.global_.log_dir
            output_dir = base / config.global_.output_dir
        elif not configured_base.is_absolute() and configured_base != Path("data"):
            base = base.parent / configured_base
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