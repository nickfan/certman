from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import typer

from certman.config import create_runtime, entry_domains
from certman.logging_ import cleanup_logs
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

_export_service = ExportService()


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
    runtime = create_runtime(data_dir=data_dir, config_file=config_file)
    ctx.obj = runtime


def _service(ctx: typer.Context) -> CertService:
    return CertService(ctx.obj)


@app.command("config-validate")
def config_validate(ctx: typer.Context):
    """Validate config and required env secrets.

    Exit code:
    - 0: valid
    - non-zero: validation failure
    """
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
    """List merged entries from config.

    Output columns: entry name, provider, primary domain, SAN domains.
    """
    runtime = ctx.obj
    for entry in runtime.config.entries:
        domains = entry_domains(entry)
        typer.echo(
            f"{entry.name}\tprovider={entry.dns_provider}\tprimary={entry.primary_domain}\tdomains={','.join(domains)}"
        )


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

    runtime = ctx.obj

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
