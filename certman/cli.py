from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import typer
import tomli_w

from certman.certbot_runner import CertbotPaths, run_certbot
from certman.config import CredentialsConfig, EntryConfig, create_runtime, entry_domains
from certman.config_admin import (
    default_config_filename,
    ensure_default_global_config,
    read_env_file,
    remove_global_entry,
    remove_item_entry,
    set_env_value,
    unset_env_value,
    upsert_global_entry,
    write_item_entry,
)
from certman.logging_ import cleanup_logs
from certman.providers import (
    AliyunCredentials,
    CloudflareCredentials,
    write_aliyun_credentials_ini,
    write_cloudflare_credentials_ini,
)
from certman.runtime_logging import new_run_logfile
from certman.services.cert_service import CertService, resolve_entry_cert_name
from certman.services.export_service import ExportService


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "CertMan local CLI. Use this entrypoint for single-host certificate operations "
        "(issue, renew, export, check, config validate, logs cleanup)."
    ),
)
config_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Config item management")
env_app = typer.Typer(add_completion=False, no_args_is_help=True, help=".env variable management")
app.add_typer(config_app, name="config")
app.add_typer(env_app, name="env")

_export_service = ExportService()


def _direct_certbot_paths(data_dir: str) -> CertbotPaths:
    base = Path(data_dir)
    run_dir = base / "run"
    letsencrypt_dir = run_dir / "letsencrypt"
    work_dir = run_dir / "work"
    logs_dir = base / "log"

    letsencrypt_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    return CertbotPaths(
        config_dir=letsencrypt_dir,
        work_dir=work_dir,
        logs_dir=logs_dir,
    )


def _derive_cert_name(domains: list[str]) -> str:
    if not domains:
        raise typer.BadParameter("must provide at least one --domain")
    for domain in domains:
        if not domain.startswith("*."):
            return domain
    return domains[0].lstrip("*.")


def _build_direct_auth(
    *,
    provider: str,
    cert_name: str,
    data_dir: str,
    access_key_id: str | None,
    access_key_secret: str | None,
    api_token: str | None,
    aws_region: str,
) -> tuple[list[str], dict[str, str | None]]:
    normalized = provider.strip().lower()
    creds_dir = Path(data_dir) / "run" / "credentials"

    if normalized == "aliyun":
        if not access_key_id or not access_key_secret:
            raise typer.BadParameter("aliyun requires --access-key-id/--access-key-secret")
        cred_file = creds_dir / f"aliyun-{cert_name}.ini"
        write_aliyun_credentials_ini(
            cred_file,
            AliyunCredentials(access_key_id=access_key_id, access_key_secret=access_key_secret),
        )
        return [
            "--authenticator",
            "dns-aliyun",
            "--dns-aliyun-credentials",
            str(cred_file),
        ], {}

    if normalized == "cloudflare":
        if not api_token:
            raise typer.BadParameter("cloudflare requires --api-token")
        cred_file = creds_dir / f"cloudflare-{cert_name}.ini"
        write_cloudflare_credentials_ini(cred_file, CloudflareCredentials(api_token=api_token))
        return [
            "--authenticator",
            "dns-cloudflare",
            "--dns-cloudflare-credentials",
            str(cred_file),
        ], {}

    if normalized == "route53":
        if not access_key_id or not access_key_secret:
            raise typer.BadParameter("route53 requires --access-key-id/--access-key-secret")
        return ["--authenticator", "dns-route53"], {
            "AWS_ACCESS_KEY_ID": access_key_id,
            "AWS_SECRET_ACCESS_KEY": access_key_secret,
            "AWS_DEFAULT_REGION": aws_region,
        }

    raise typer.BadParameter("service-provider must be aliyun/cloudflare/route53")


def _run_oneshot_certbot(
    *,
    action: Literal["issue", "renew"],
    ctx: typer.Context,
    domains: list[str],
    provider: str,
    email: str,
    output_dir: str,
    cert_name: str | None,
    acme_server: Literal["staging", "prod"],
    access_key_id: str | None,
    access_key_secret: str | None,
    api_token: str | None,
    aws_region: str,
    force: bool,
    verbose: bool,
) -> None:
    data_dir = str(ctx.meta.get("data_dir", "data"))
    paths = _direct_certbot_paths(data_dir)
    actual_cert_name = cert_name or _derive_cert_name(domains)

    auth_args, env_overrides = _build_direct_auth(
        provider=provider,
        cert_name=actual_cert_name,
        data_dir=data_dir,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        api_token=api_token,
        aws_region=aws_region,
    )

    args: list[str] = [
        "certonly",
        *auth_args,
        "--agree-tos",
        "--email",
        email,
        "--cert-name",
        actual_cert_name,
    ]
    if acme_server == "staging":
        args.append("--test-cert")
    if force:
        args.append("--force-renewal")
    for domain in domains:
        args.extend(["-d", domain])

    result = run_certbot(args, paths=paths, passthrough=verbose, env=env_overrides or None)
    log_path = new_run_logfile(paths.logs_dir, command=f"oneshot_{action}")
    log_payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "command": f"oneshot-{action}",
        "domains": domains,
        "provider": provider,
        "cert_name": actual_cert_name,
        "output_dir": output_dir,
        "certbot": {
            "returncode": result.returncode,
            "cmd": result.cmd,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    }
    log_path.write_text(json.dumps(log_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if not result.ok:
        if result.is_admin_required_error():
            typer.echo("certbot requires Windows administrative rights.")
        typer.echo(result.stderr or result.stdout or "certbot failed")
        typer.echo(f"log={log_path}")
        raise typer.Exit(code=2 if result.is_admin_required_error() else 1)

    export_result = _export_service.export_from_live(
        letsencrypt_live_dir=paths.config_dir / "live" / actual_cert_name,
        output_entry_dir=Path(output_dir),
        overwrite=True,
    )
    if not export_result.success:
        typer.echo(f"export failed: {export_result.error}")
        typer.echo(f"log={log_path}")
        raise typer.Exit(code=1)

    typer.echo(
        f"ok: {action} completed cert_name={actual_cert_name} provider={provider} domains={','.join(domains)}"
    )
    typer.echo(f"output_dir={output_dir}")
    typer.echo(f"log={log_path}")


@app.callback()
def _callback(
    ctx: typer.Context,
    data_dir: str = typer.Option(
        "data",
        "--data-dir",
        "-D",
        help="Base data directory",
        envvar="CERTMAN_DATA_DIR",
    ),
    config_file: str | None = typer.Option(
        None,
        "--config-file",
        "-c",
        help="Global config filename under <data_dir>/conf (default: config.toml)",
        envvar="CERTMAN_CONFIG_FILE",
    ),
):
    """Initialize runtime for local commands.

    Examples:
    - certman -D data entries
    - certman -D data -c config.toml check --warn-days 30
    """
    resolved_config_file = config_file or os.getenv("CERTMAN_CONFIG_FILE") or default_config_filename()
    ctx.meta["data_dir"] = data_dir
    ctx.meta["config_file"] = config_file
    ctx.meta["config_filename"] = resolved_config_file
    try:
        runtime = create_runtime(data_dir=data_dir, config_file=config_file)
        ctx.obj = runtime
    except FileNotFoundError:
        raw_args = list(ctx.args or [])
        is_config_init = "config" in raw_args and "init" in raw_args
        if not is_config_init:
            ctx.obj = None
            return
        data_path = Path(data_dir)
        stub = SimpleNamespace(paths=SimpleNamespace(conf_dir=data_path / "conf"))
        ctx.obj = stub


def _service(ctx: typer.Context) -> CertService:
    return CertService(_runtime(ctx))


def _runtime(ctx: typer.Context):
    runtime = ctx.obj
    if runtime is not None and hasattr(runtime, "config"):
        return runtime

    data_dir = str(ctx.meta.get("data_dir", "data"))
    config_file = ctx.meta.get("config_file")
    try:
        runtime = create_runtime(data_dir=data_dir, config_file=config_file)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    ctx.obj = runtime
    return runtime


def _config_filename(ctx: typer.Context) -> str:
    return str(ctx.meta.get("config_filename", default_config_filename()))


def _parse_storage(storage: str) -> str:
    normalized = storage.strip().lower()
    if normalized not in {"item", "global"}:
        raise typer.BadParameter("storage must be item or global")
    return normalized


def _parse_wildcard_option(raw_value: str | None) -> bool | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise typer.BadParameter("wildcard must be true/false")


@app.command("config-validate")
def config_validate(
    ctx: typer.Context,
    name: list[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Validate only the specified entry name; repeat to validate multiple entries",
    ),
    all: bool = typer.Option(
        False,
        "--all",
        help="Validate all merged entries",
    ),
):
    """Validate config and required env secrets with explicit scope.

    Scope rules:
    - Must provide at least one --name or use --all
    - --name and --all cannot be combined

    Exit code:
    - 0: valid
    - non-zero: validation failure
    """
    if all and name:
        raise typer.BadParameter("cannot combine --all with --name")
    if not all and not name:
        raise typer.BadParameter("must specify at least one --name or use --all")

    runtime = _runtime(ctx)
    try:
        runtime.config.validate_required_secrets(
            runtime.env,
            entry_names=list(name or []),
            validate_all=all,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo("OK")


@app.command("logs-clean")
def logs_clean(
    ctx: typer.Context,
    keep_days: int = typer.Option(
        30, "--keep-days", "-k", help="Keep latest N days logs"
    ),
):
    """Cleanup old logs under data/log."""
    runtime = _runtime(ctx)
    removed = cleanup_logs(runtime.paths.log_dir, keep_days=keep_days)
    typer.echo(f"Removed {removed} old log file(s)")


@app.command("entries")
def entries(ctx: typer.Context):
    """List merged entries from config.

    Output columns: entry name, provider, primary domain, SAN domains.
    """
    runtime = _runtime(ctx)
    for entry in runtime.config.entries:
        domains = entry_domains(entry)
        typer.echo(
            f"{entry.name}\tprovider={entry.dns_provider}\tprimary={entry.primary_domain}\tdomains={','.join(domains)}"
        )


@config_app.command("list")
def config_list(ctx: typer.Context, json_output: bool = typer.Option(False, "--json", help="Output JSON")) -> None:
    """List merged config entries."""
    runtime = _runtime(ctx)
    items = [
        {
            "name": entry.name,
            "dns_provider": entry.dns_provider,
            "primary_domain": entry.primary_domain,
            "domains": entry_domains(entry),
            "account_id": entry.account_id,
        }
        for entry in runtime.config.entries
    ]
    if json_output:
        typer.echo(json.dumps(items, ensure_ascii=False))
        return
    for item in items:
        typer.echo(
            f"{item['name']}\tprovider={item['dns_provider']}\tprimary={item['primary_domain']}"
            f"\taccount_id={item['account_id'] or '-'}\tdomains={','.join(item['domains'])}"
        )


@config_app.command("show")
def config_show(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Entry name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show one merged config entry."""
    runtime = _runtime(ctx)
    entry = next((entry for entry in runtime.config.entries if entry.name == name), None)
    if entry is None:
        raise typer.BadParameter(f"entry not found: {name}")
    payload = entry.model_dump(exclude_none=True)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _build_entry_from_args(
    *,
    name: str,
    primary_domain: str,
    dns_provider: str,
    description: str,
    secondary_domains: list[str],
    wildcard: bool,
    account_id: str | None,
    access_key_id: str | None,
    access_key_secret: str | None,
    api_token: str | None,
) -> EntryConfig:
    return EntryConfig.model_validate(
        {
            "name": name,
            "description": description,
            "primary_domain": primary_domain,
            "secondary_domains": secondary_domains,
            "wildcard": wildcard,
            "dns_provider": dns_provider,
            "account_id": account_id,
            "credentials": CredentialsConfig(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                api_token=api_token,
            ).model_dump(exclude_none=True),
        }
    )


@config_app.command("add")
def config_add(
    ctx: typer.Context,
    name: str | None = typer.Option(None, "--name", "-n", help="Entry name"),
    primary_domain: str | None = typer.Option(None, "--primary-domain", help="Primary domain"),
    dns_provider: str | None = typer.Option(None, "--dns-provider", help="Provider: aliyun|cloudflare|route53"),
    description: str = typer.Option("", "--description", help="Entry description"),
    secondary_domain: list[str] = typer.Option(None, "--secondary-domain", help="Secondary domain, repeatable"),
    wildcard: str | None = typer.Option(None, "--wildcard", help="Wildcard true/false"),
    account_id: str | None = typer.Option(None, "--account-id", help="Provider account id"),
    access_key_id: str | None = typer.Option(None, "--access-key-id", help="Credential access key id"),
    access_key_secret: str | None = typer.Option(None, "--access-key-secret", help="Credential secret key"),
    api_token: str | None = typer.Option(None, "--api-token", help="Cloudflare token"),
    storage: str = typer.Option("item", "--storage", help="Storage mode: item|global"),
    interactive: bool = typer.Option(False, "--interactive", help="Prompt for missing fields"),
) -> None:
    """Add one config entry into item file or global config."""
    runtime = _runtime(ctx)
    chosen_storage = _parse_storage(storage)

    if interactive:
        name = name or typer.prompt("Entry name")
        primary_domain = primary_domain or typer.prompt("Primary domain")
        dns_provider = dns_provider or typer.prompt("DNS provider (aliyun/cloudflare/route53)")
        if wildcard is None:
            wildcard = "true" if typer.confirm("Enable wildcard", default=True) else "false"
        if account_id is None:
            account_id = typer.prompt("Account ID (optional)", default="") or None

    if not name or not primary_domain or not dns_provider:
        raise typer.BadParameter("name, primary-domain, dns-provider are required (or use --interactive)")

    wildcard_bool = _parse_wildcard_option(wildcard)
    entry = _build_entry_from_args(
        name=name,
        primary_domain=primary_domain,
        dns_provider=dns_provider,
        description=description,
        secondary_domains=list(secondary_domain or []),
        wildcard=True if wildcard_bool is None else wildcard_bool,
        account_id=account_id,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        api_token=api_token,
    )

    if chosen_storage == "item":
        path = write_item_entry(runtime.paths.conf_dir, entry)
        typer.echo(f"added entry={entry.name} storage=item path={path}")
        return

    path, created = upsert_global_entry(runtime.paths.conf_dir, _config_filename(ctx), entry)
    action = "added" if created else "updated"
    typer.echo(f"{action} entry={entry.name} storage=global path={path}")


@config_app.command("remove")
def config_remove(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Entry name"),
    storage: str = typer.Option("item", "--storage", help="Storage mode: item|global"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove config entry from item file or global config."""
    runtime = _runtime(ctx)
    chosen_storage = _parse_storage(storage)
    if not yes and not typer.confirm(f"Remove entry '{name}' from {chosen_storage} storage", default=False):
        typer.echo("cancelled")
        return

    if chosen_storage == "item":
        removed = remove_item_entry(runtime.paths.conf_dir, name)
        if not removed:
            raise typer.BadParameter(f"item entry not found: {name}")
        typer.echo(f"removed entry={name} storage=item")
        return

    path, removed = remove_global_entry(runtime.paths.conf_dir, _config_filename(ctx), name)
    if not removed:
        raise typer.BadParameter(f"global entry not found: {name}")
    typer.echo(f"removed entry={name} storage=global path={path}")


@config_app.command("edit")
def config_edit(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Entry name"),
    primary_domain: str | None = typer.Option(None, "--primary-domain", help="Primary domain"),
    description: str | None = typer.Option(None, "--description", help="Entry description"),
    secondary_domain: list[str] = typer.Option(None, "--secondary-domain", help="Secondary domain, repeatable"),
    wildcard: str | None = typer.Option(None, "--wildcard", help="Wildcard true/false"),
    dns_provider: str | None = typer.Option(None, "--dns-provider", help="Provider: aliyun|cloudflare|route53"),
    account_id: str | None = typer.Option(None, "--account-id", help="Provider account id"),
    storage: str = typer.Option("item", "--storage", help="Storage mode: item|global"),
    interactive: bool = typer.Option(False, "--interactive", help="Prompt to edit key fields"),
) -> None:
    """Edit one existing config entry (write into selected storage)."""
    runtime = _runtime(ctx)
    chosen_storage = _parse_storage(storage)
    existing = next((entry for entry in runtime.config.entries if entry.name == name), None)
    if existing is None:
        raise typer.BadParameter(f"entry not found: {name}")

    new_primary = primary_domain if primary_domain is not None else existing.primary_domain
    new_provider = dns_provider if dns_provider is not None else existing.dns_provider
    new_desc = description if description is not None else existing.description
    new_domains = list(secondary_domain) if secondary_domain else list(existing.secondary_domains)
    wildcard_raw = wildcard
    if interactive:
        new_primary = typer.prompt("Primary domain", default=new_primary)
        new_provider = typer.prompt("DNS provider", default=new_provider)
        new_desc = typer.prompt("Description", default=new_desc)
        wildcard_raw = "true" if typer.confirm("Enable wildcard", default=existing.wildcard) else "false"
        account_id = typer.prompt("Account ID", default=account_id or existing.account_id or "") or None

    wildcard_bool = _parse_wildcard_option(wildcard_raw)
    entry = _build_entry_from_args(
        name=name,
        primary_domain=new_primary,
        dns_provider=new_provider,
        description=new_desc,
        secondary_domains=new_domains,
        wildcard=existing.wildcard if wildcard_bool is None else wildcard_bool,
        account_id=account_id if account_id is not None else existing.account_id,
        access_key_id=existing.credentials.access_key_id,
        access_key_secret=existing.credentials.access_key_secret,
        api_token=existing.credentials.api_token,
    )

    if chosen_storage == "item":
        path = write_item_entry(runtime.paths.conf_dir, entry)
        typer.echo(f"updated entry={name} storage=item path={path}")
        return

    path, _ = upsert_global_entry(runtime.paths.conf_dir, _config_filename(ctx), entry)
    typer.echo(f"updated entry={name} storage=global path={path}")


@config_app.command("init")
def config_init(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Overwrite existing config file"),
    interactive: bool = typer.Option(True, "--interactive/--non-interactive", help="Use guided setup"),
    with_env: bool = typer.Option(True, "--with-env/--no-env", help="Create .env placeholder file"),
) -> None:
    """Initialize baseline config and optional .env placeholders."""
    config_filename = _config_filename(ctx)
    data_dir = Path(str(ctx.meta.get("data_dir", "data")))
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True, exist_ok=True)
    target_path = conf_dir / config_filename

    if target_path.exists() and not force:
        raise typer.BadParameter(f"config file exists: {target_path} (use --force)")

    if config_filename == default_config_filename():
        ensure_default_global_config(conf_dir, overwrite=force)
    else:
        base = {
            "run_mode": "local",
            "global": {
                "data_dir": "data",
                "conf_dir": "conf",
                "run_dir": "run",
                "log_dir": "log",
                "output_dir": "output",
                "letsencrypt_dir": "letsencrypt",
                "acme_server": "staging",
                "email": "admin@example.com",
                "scan_items_glob": "item_*.toml",
            },
        }
        target_path.write_text(tomli_w.dumps(base), encoding="utf-8")

    if interactive and typer.confirm("Create an example item entry", default=True):
        name = typer.prompt("Entry name", default="example")
        primary_domain = typer.prompt("Primary domain", default="example.com")
        provider = typer.prompt("DNS provider", default="aliyun")
        account_id = typer.prompt("Account ID", default="example")
        entry = _build_entry_from_args(
            name=name,
            primary_domain=primary_domain,
            dns_provider=provider,
            description="",
            secondary_domains=[],
            wildcard=True,
            account_id=account_id,
            access_key_id=None,
            access_key_secret=None,
            api_token=None,
        )
        write_item_entry(conf_dir, entry)

    if with_env:
        env_path = conf_dir / ".env"
        if not env_path.exists() or force:
            env_path.write_text("# CERTMAN_* provider credentials\n", encoding="utf-8")

    typer.echo(f"initialized config path={target_path}")


@env_app.command("list")
def env_list(ctx: typer.Context, json_output: bool = typer.Option(False, "--json", help="Output JSON")) -> None:
    """List keys in data/conf/.env."""
    runtime = _runtime(ctx)
    env_path, values = read_env_file(runtime.paths.conf_dir)
    if json_output:
        typer.echo(json.dumps({"path": str(env_path), "values": values}, ensure_ascii=False))
        return
    typer.echo(f"path={env_path}")
    for key in sorted(values.keys()):
        typer.echo(f"{key}=***")


@env_app.command("set")
def env_set(
    ctx: typer.Context,
    key: str = typer.Option(..., "--key", help="Environment variable key"),
    value: str = typer.Option(..., "--value", help="Environment variable value"),
) -> None:
    """Set one key=value into data/conf/.env."""
    runtime = _runtime(ctx)
    path = set_env_value(runtime.paths.conf_dir, key, value)
    typer.echo(f"set key={key} path={path}")


@env_app.command("unset")
def env_unset(
    ctx: typer.Context,
    key: str = typer.Option(..., "--key", help="Environment variable key"),
) -> None:
    """Remove one key from data/conf/.env."""
    runtime = _runtime(ctx)
    path, removed = unset_env_value(runtime.paths.conf_dir, key)
    if not removed:
        raise typer.BadParameter(f"key not found: {key}")
    typer.echo(f"unset key={key} path={path}")


@app.command("new")
def new(
    ctx: typer.Context,
    name: str = typer.Option(
        ..., "--name", "-n", help="Entry name defined in config.entries"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-issue even if a valid certificate already exists"
    ),
    export_: bool = typer.Option(
        True,
        "--export/--no-export",
        help="Export artifacts to output after success",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Stream certbot output to terminal (useful for debugging)",
    ),
):
    """Issue (new) certificate for an entry.

    Typical flow:
    1) certman new --name <entry>
    2) certman export --name <entry>
    """
    try:
        result = _service(ctx).issue(name, force=force, verbose=verbose)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if not result.success:
        if result.admin_required:
            typer.echo("certbot requires Windows administrative rights.")
            typer.echo(
                "Next steps: run in Administrator shell; or use gsudo; "
                "or switch to WSL; or switch to docker-compose."
            )
            typer.echo(f"log={result.log_path}")
            raise typer.Exit(code=2)

        typer.echo(result.error or "certbot failed")
        typer.echo(f"log={result.log_path}")
        raise typer.Exit(code=1)

    typer.echo(f"ok: issued entry={result.entry_name} domains={','.join(result.domains)}")
    typer.echo(f"log={result.log_path}")

    if export_:
        export(ctx, all=False, name=name, overwrite=True)


@app.command("oneshot-issue")
def oneshot_issue(
    ctx: typer.Context,
    domain: list[str] = typer.Option(..., "--domain", "-d", help="Domain to request (repeatable)"),
    service_provider: str = typer.Option(..., "--service-provider", "--sp", "-sp", help="aliyun|cloudflare|route53"),
    email: str = typer.Option(..., "--email", help="ACME account email"),
    output: str = typer.Option(..., "--output", "-o", help="Output directory for cert artifacts"),
    cert_name: str | None = typer.Option(None, "--cert-name", help="Certbot cert name (default derives from domains)"),
    acme_server: Literal["staging", "prod"] = typer.Option("prod", "--acme-server", help="ACME server"),
    access_key_id: str | None = typer.Option(None, "--access-key-id", "--ak", help="Provider access key id"),
    access_key_secret: str | None = typer.Option(None, "--access-key-secret", "--sk", help="Provider secret key"),
    api_token: str | None = typer.Option(None, "--api-token", help="Cloudflare API token"),
    aws_region: str = typer.Option("us-east-1", "--aws-region", help="Route53 region"),
    force: bool = typer.Option(False, "--force", help="Force renewal semantics on certonly"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Stream certbot output"),
) -> None:
    """Issue certificate in pure CLI mode without config files."""
    _run_oneshot_certbot(
        action="issue",
        ctx=ctx,
        domains=list(domain),
        provider=service_provider,
        email=email,
        output_dir=output,
        cert_name=cert_name,
        acme_server=acme_server,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        api_token=api_token,
        aws_region=aws_region,
        force=force,
        verbose=verbose,
    )


@app.command("oneshot-renew")
def oneshot_renew(
    ctx: typer.Context,
    domain: list[str] = typer.Option(..., "--domain", "-d", help="Domain to renew (repeatable)"),
    service_provider: str = typer.Option(..., "--service-provider", "--sp", "-sp", help="aliyun|cloudflare|route53"),
    email: str = typer.Option(..., "--email", help="ACME account email"),
    output: str = typer.Option(..., "--output", "-o", help="Output directory for cert artifacts"),
    cert_name: str | None = typer.Option(None, "--cert-name", help="Certbot cert name (default derives from domains)"),
    acme_server: Literal["staging", "prod"] = typer.Option("prod", "--acme-server", help="ACME server"),
    access_key_id: str | None = typer.Option(None, "--access-key-id", "--ak", help="Provider access key id"),
    access_key_secret: str | None = typer.Option(None, "--access-key-secret", "--sk", help="Provider secret key"),
    api_token: str | None = typer.Option(None, "--api-token", help="Cloudflare API token"),
    aws_region: str = typer.Option("us-east-1", "--aws-region", help="Route53 region"),
    force: bool = typer.Option(True, "--force/--no-force", help="Force renew semantics for one-shot run"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Stream certbot output"),
) -> None:
    """Renew certificate in pure CLI mode without config files."""
    _run_oneshot_certbot(
        action="renew",
        ctx=ctx,
        domains=list(domain),
        provider=service_provider,
        email=email,
        output_dir=output,
        cert_name=cert_name,
        acme_server=acme_server,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        api_token=api_token,
        aws_region=aws_region,
        force=force,
        verbose=verbose,
    )


@app.command("renew")
def renew(
    ctx: typer.Context,
    all: bool = typer.Option(False, "--all", "-a", help="Renew all configured entries"),
    name: str | None = typer.Option(None, "--name", "-n", help="Renew one specific entry"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force renew even if certbot does not consider it due"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Test renew flow against staging without saving certs",
    ),
    export_: bool = typer.Option(
        True,
        "--export/--no-export",
        help="Export artifacts to output after success",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Stream certbot output to terminal (useful for debugging)",
    ),
):
    """Renew certificates using `certbot renew`.

    Certbot will reuse the authenticator/options stored in each renewal config.
    """
    try:
        results = _service(ctx).renew(
            all=all,
            name=name,
            force=force,
            dry_run=dry_run,
            verbose=verbose,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if not results:
        raise typer.BadParameter("no entries configured")

    successes = [result for result in results if result.success]
    failures = [result for result in results if not result.success]
    admin_failures = [result for result in failures if result.admin_required]

    for result in successes:
        msg = f"ok: renewed entry={result.entry_name}"
        if result.dry_run:
            msg += " (dry-run)"
        typer.echo(msg)
        typer.echo(f"log={result.log_path}")

    for result in failures:
        if result.admin_required:
            typer.echo("certbot requires Windows administrative rights.")
            typer.echo(
                "Next steps: run in Administrator shell; or use gsudo; "
                "or switch to WSL; or switch to docker-compose."
            )
        else:
            typer.echo(result.error or "certbot renew failed")
        typer.echo(f"entry={result.entry_name} log={result.log_path}")

    if export_ and not dry_run and not failures:
        for result in successes:
            export(ctx, all=False, name=result.entry_name, overwrite=True)

    if failures:
        raise typer.Exit(code=2 if admin_failures else 1)

    if all:
        msg = f"ok: renew completed count={len(successes)}"
    else:
        msg = "ok: renew completed"
    if dry_run:
        msg += " (dry-run)"
    typer.echo(msg)


@app.command("export")
def export(
    ctx: typer.Context,
    all: bool = typer.Option(False, "--all", "-a", help="Export all configured entries"),
    name: str | None = typer.Option(None, "--name", "-n", help="Export one specific entry"),
    overwrite: bool = typer.Option(
        True, "--overwrite/--no-overwrite", help="Overwrite files in output"
    ),
):
    """Export cert/key from certbot state into data/output."""
    runtime = _runtime(ctx)
    if not all and not name:
        raise typer.BadParameter("must provide --all or --name")

    targets = runtime.config.entries
    if name:
        targets = [e for e in targets if e.name == name]
        if not targets:
            raise typer.BadParameter(f"entry not found: {name}")

    letsencrypt_dir = runtime.paths.run_dir / runtime.config.global_.letsencrypt_dir

    copied_total = 0
    copied_paths: list[Path] = []
    failed_entries: list[str] = []
    for entry in targets:
        try:
            cert_name = resolve_entry_cert_name(runtime, entry, require_existing_lineage=True)
        except ValueError as exc:
            failed_entries.append(f"entry={entry.name} error={exc}")
            continue

        live_dir = letsencrypt_dir / "live" / cert_name
        out_dir = runtime.paths.output_dir / entry.name
        export_result = _export_service.export_from_live(
            letsencrypt_live_dir=live_dir,
            output_entry_dir=out_dir,
            overwrite=overwrite,
        )
        if not export_result.success:
            failed_entries.append(
                f"entry={entry.name} {export_result.error or 'export failed'}"
            )
            continue

        copied = export_result.copied_paths
        copied_total += len(copied)
        copied_paths.extend(copied)
        if not copied:
            failed_entries.append(f"entry={entry.name} no files exported")

    if copied_total == 0:
        for entry_name in failed_entries:
            typer.echo(entry_name)
        typer.echo("No certificate files were exported")
        raise typer.Exit(code=1)

    if failed_entries:
        typer.echo(f"Exported {copied_total} file(s)")
        for entry_name in failed_entries:
            typer.echo(entry_name)
        raise typer.Exit(code=1)

    typer.echo(f"Exported {copied_total} file(s)")
    if copied_paths:
        typer.echo(f"output_dir={runtime.paths.output_dir}")
        for p in copied_paths:
            rel = p
            try:
                rel = p.relative_to(runtime.paths.data_dir)
            except ValueError:
                pass
            typer.echo(f"- {rel}")


@app.command("check")
def check(
    ctx: typer.Context,
    warn_days: int = typer.Option(
        30, "--warn-days", "-w", help="Warn when expires within N days"
    ),
    force_renew_days: int = typer.Option(
        7, "--force-renew-days", "-F", help="Fail when expires within N days"
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="Check one specific entry"),
    fix: bool = typer.Option(False, "--fix", help="Auto-fix by running new/renew"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check certificate expiry only; do not auto-renew.

    Exit codes (cron-friendly):
    - 0: OK
    - 10: warning (<= warn_days)
    - 20: force-renew needed (<= force_renew_days or already expired)
    - 30: missing cert files / entry not found
    """

    runtime = _runtime(ctx)

    results = _service(ctx).check(
        warn_days=warn_days,
        force_renew_days=force_renew_days,
        name=name,
    )

    worst_code = 0
    for result in results:
        if result["status"] == "missing":
            worst_code = max(worst_code, 30)
        elif result["status"] == "force-renew":
            worst_code = max(worst_code, 20)
        elif result["status"] == "warn":
            worst_code = max(worst_code, 10)

    log_path = new_run_logfile(runtime.paths.log_dir, command="check")
    fix_actions: list[dict] = []

    if fix:
        for r in results:
            if r["status"] == "missing" and r.get("reason") in {None, "cert-missing"}:
                fix_actions.append(
                    {
                        "entry": r["entry"],
                        "action": "new",
                        "force": True,
                        "reason": "missing",
                    }
                )
            elif r["status"] == "force-renew":
                fix_actions.append(
                    {
                        "entry": r["entry"],
                        "action": "renew",
                        "force": True,
                        "reason": "expires-soon",
                    }
                )

        # Execute planned actions.
        for action in fix_actions:
            if action["action"] == "new":
                new(ctx, name=action["entry"], force=True, export_=True)
            elif action["action"] == "renew":
                renew(ctx, all=False, name=action["entry"], force=True, export_=True)

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "warn_days": warn_days,
        "force_renew_days": force_renew_days,
        "results": results,
        "fix": fix,
        "fix_actions": fix_actions,
        "exit_code": worst_code,
    }
    log_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        for r in results:
            if r["status"] == "missing":
                message = f"[{r['status']}] {r['entry']} {r.get('primary_domain') or '-'}"
                if r.get("reason"):
                    message += f" reason={r['reason']}"
                if r.get("error"):
                    message += f" error={r['error']}"
                if r.get("cert_path"):
                    message += f" cert={r['cert_path']}"
                typer.echo(message)
            else:
                typer.echo(
                    f"[{r['status']}] {r['entry']} {r['primary_domain']} days_left={r['days_left']} not_after={r['not_after']}"
                )
        typer.echo(f"log={log_path}")

    if fix and fix_actions:
        typer.echo("fix actions:")
        for a in fix_actions:
            typer.echo(f"- {a['action']} --name {a['entry']} --force")

    raise typer.Exit(code=worst_code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
