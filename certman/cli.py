from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import typer

from certman.certbot_runner import CertbotPaths, run_certbot
from certman.certs import get_cert_status
from certman.config import create_runtime
from certman.exporter import export_entry
from certman.logging_ import cleanup_logs
from certman.providers import (
    aliyun_credentials_for_entry,
    write_aliyun_credentials_ini,
)
from certman.runtime_logging import new_run_logfile


def _entry_domains(entry) -> list[str]:
    domains = [entry.primary_domain, *entry.secondary_domains]
    if entry.wildcard:
        domains.append(f"*.{entry.primary_domain}")
    # de-dup while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for d in domains:
        if d in seen:
            continue
        seen.add(d)
        unique.append(d)
    return unique


def _write_command_log(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _prepare_aliyun_credentials_ini(*, runtime, entry) -> Path:
    creds = aliyun_credentials_for_entry(entry)
    cred_dir = runtime.paths.run_dir / "credentials"
    cred_file = cred_dir / f"aliyun_{(entry.account_id or entry.name)}.ini"
    write_aliyun_credentials_ini(cred_file, creds)
    return cred_file


app = typer.Typer(add_completion=False)


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
    runtime = create_runtime(data_dir=data_dir, config_file=config_file)
    ctx.obj = runtime


@app.command("config-validate")
def config_validate(ctx: typer.Context):
    """Validate config and required env secrets."""
    runtime = ctx.obj
    runtime.config.validate_required_secrets(runtime.env)
    typer.echo("OK")


@app.command("logs-clean")
def logs_clean(
    ctx: typer.Context,
    keep_days: int = typer.Option(
        30, "--keep-days", "-k", help="Keep latest N days logs"
    ),
):
    """Cleanup old logs under data/log."""
    runtime = ctx.obj
    removed = cleanup_logs(runtime.paths.log_dir, keep_days=keep_days)
    typer.echo(f"Removed {removed} old log file(s)")


@app.command("entries")
def entries(ctx: typer.Context):
    """List merged entries from config."""
    runtime = ctx.obj
    for entry in runtime.config.entries:
        domains = _entry_domains(entry)
        typer.echo(
            f"{entry.name}\tprovider={entry.dns_provider}\tprimary={entry.primary_domain}\tdomains={','.join(domains)}"
        )


@app.command("new")
def new(
    ctx: typer.Context,
    name: str = typer.Option(
        ..., "--name", "-n", help="Issue a new certificate for one entry"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-issue even if exists"
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
    """Issue (new) certificate for an entry."""
    runtime = ctx.obj
    targets = [e for e in runtime.config.entries if e.name == name]
    if not targets:
        raise typer.BadParameter(f"entry not found: {name}")
    entry = targets[0]

    letsencrypt_dir = runtime.paths.run_dir / runtime.config.global_.letsencrypt_dir
    paths = CertbotPaths(
        config_dir=letsencrypt_dir,
        work_dir=runtime.paths.run_dir / "work",
        logs_dir=runtime.paths.log_dir,
    )

    provider = entry.dns_provider.lower()
    if provider != "aliyun":
        raise typer.BadParameter(
            f"unsupported dns_provider for now: {entry.dns_provider}"
        )

    cred_file = _prepare_aliyun_credentials_ini(runtime=runtime, entry=entry)

    domains = _entry_domains(entry)

    args: list[str] = [
        "certonly",
        "--authenticator",
        "dns-aliyun",
        "--dns-aliyun-credentials",
        str(cred_file),
        "--agree-tos",
        "--email",
        runtime.config.global_.email,
    ]

    if runtime.config.global_.acme_server == "staging":
        args.append("--test-cert")

    if force:
        args.append("--force-renewal")

    for d in domains:
        args.extend(["-d", d])

    log_path = new_run_logfile(runtime.paths.log_dir, command="new")
    result = run_certbot(args, paths=paths, passthrough=verbose)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "command": "new",
        "entry": entry.name,
        "domains": domains,
        "provider": provider,
        "certbot": {
            "returncode": result.returncode,
            "cmd": result.cmd,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    }

    if not result.ok and result.is_admin_required_error():
        payload["hint"] = {
            "reason": "windows_admin_required",
            "suggestions": [
                "Re-run in elevated (Administrator) shell",
                "Or use gsudo to elevate: gsudo <same command>",
                "Or switch to WSL runner (recommended on Windows)",
                "Or switch to docker-compose runner and mount /data",
            ],
        }

    _write_command_log(log_path, payload)

    if not result.ok:
        if result.is_admin_required_error():
            typer.echo("certbot requires Windows administrative rights.")
            typer.echo(
                "Next steps: run in Administrator shell; or use gsudo; "
                "or switch to WSL; or switch to docker-compose."
            )
            typer.echo(f"log={log_path}")
            raise typer.Exit(code=2)

        typer.echo("certbot failed")
        typer.echo(f"log={log_path}")
        raise typer.Exit(code=1)

    typer.echo(f"ok: issued entry={entry.name} domains={','.join(domains)}")
    typer.echo(f"log={log_path}")

    if export_:
        export(ctx, all=False, name=name, overwrite=True)


@app.command("renew")
def renew(
    ctx: typer.Context,
    all: bool = typer.Option(False, "--all", "-a", help="Renew all entries"),
    name: str | None = typer.Option(None, "--name", "-n", help="Renew a single entry"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force renew even if not due"
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
    runtime = ctx.obj
    if not all and not name:
        raise typer.BadParameter("must provide --all or --name")

    letsencrypt_dir = runtime.paths.run_dir / runtime.config.global_.letsencrypt_dir
    paths = CertbotPaths(
        config_dir=letsencrypt_dir,
        work_dir=runtime.paths.run_dir / "work",
        logs_dir=runtime.paths.log_dir,
    )

    args: list[str] = ["renew"]

    if all:
        for entry in runtime.config.entries:
            _prepare_aliyun_credentials_ini(runtime=runtime, entry=entry)

    if name and not all:
        targets = [e for e in runtime.config.entries if e.name == name]
        if not targets:
            raise typer.BadParameter(f"entry not found: {name}")
        _prepare_aliyun_credentials_ini(runtime=runtime, entry=targets[0])
        args.extend(["--cert-name", targets[0].primary_domain])

    if force:
        args.append("--force-renewal")

    if dry_run:
        args.append("--dry-run")

    log_path = new_run_logfile(runtime.paths.log_dir, command="renew")
    result = run_certbot(args, paths=paths, passthrough=verbose)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "command": "renew",
        "args": args,
        "certbot": {
            "returncode": result.returncode,
            "cmd": result.cmd,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    }
    _write_command_log(log_path, payload)

    if not result.ok:
        if result.is_admin_required_error():
            typer.echo("certbot requires Windows administrative rights.")
            typer.echo(
                "Next steps: run in Administrator shell; or use gsudo; "
                "or switch to WSL; or switch to docker-compose."
            )
            typer.echo(f"log={log_path}")
            raise typer.Exit(code=2)

        typer.echo("certbot renew failed")
        typer.echo(f"log={log_path}")
        raise typer.Exit(code=1)

    msg = "ok: renew completed"
    if dry_run:
        msg += " (dry-run)"
    typer.echo(msg)
    typer.echo(f"log={log_path}")

    if export_ and not dry_run:
        if name and not all:
            export(ctx, all=False, name=name, overwrite=True)
        else:
            export(ctx, all=True, name=None, overwrite=True)


@app.command("export")
def export(
    ctx: typer.Context,
    all: bool = typer.Option(False, "--all", "-a", help="Export all entries"),
    name: str | None = typer.Option(None, "--name", "-n", help="Export a single entry"),
    overwrite: bool = typer.Option(
        True, "--overwrite/--no-overwrite", help="Overwrite files in output"
    ),
):
    """Export cert/key from certbot state into data/output."""
    runtime = ctx.obj
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
    for entry in targets:
        live_dir = letsencrypt_dir / "live" / entry.primary_domain
        out_dir = runtime.paths.output_dir / entry.name
        copied = export_entry(
            letsencrypt_live_dir=live_dir,
            output_entry_dir=out_dir,
            overwrite=overwrite,
        )
        copied_total += len(copied)
        copied_paths.extend(copied)

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
    name: str | None = typer.Option(None, "--name", "-n", help="Check a single entry"),
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

    runtime = ctx.obj

    targets = runtime.config.entries
    if name:
        targets = [e for e in targets if e.name == name]
        if not targets:
            raise typer.BadParameter(f"entry not found: {name}")

    letsencrypt_dir = runtime.paths.run_dir / runtime.config.global_.letsencrypt_dir

    results: list[dict] = []
    worst_code = 0

    for entry in targets:
        cert_path = letsencrypt_dir / "live" / entry.primary_domain / "cert.pem"
        if not cert_path.exists():
            results.append(
                {
                    "entry": entry.name,
                    "primary_domain": entry.primary_domain,
                    "status": "missing",
                    "cert_path": str(cert_path),
                }
            )
            worst_code = max(worst_code, 30)
            continue

        status = get_cert_status(cert_path)
        days_left = status.days_left

        state = "ok"
        code = 0
        if days_left <= force_renew_days:
            state = "force-renew"
            code = 20
        elif days_left <= warn_days:
            state = "warn"
            code = 10

        results.append(
            {
                "entry": entry.name,
                "primary_domain": entry.primary_domain,
                "status": state,
                "days_left": days_left,
                "not_after": status.not_after.isoformat(),
                "cert_path": str(cert_path),
            }
        )
        worst_code = max(worst_code, code)

    log_path = new_run_logfile(runtime.paths.log_dir, command="check")
    fix_actions: list[dict] = []

    if fix:
        for r in results:
            if r["status"] == "missing":
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
                typer.echo(
                    f"[{r['status']}] {r['entry']} {r['primary_domain']} cert={r['cert_path']}"
                )
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
