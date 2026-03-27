from __future__ import annotations

from datetime import datetime, timezone
import time

import typer

from certman.config import create_runtime, resolve_runtime_path
from certman.scheduler.jobs import schedule_due_renewals

app = typer.Typer(add_completion=False)


def _parse_cron_field(token: str, minimum: int, maximum: int) -> set[int]:
    token = token.strip()
    if token == "*":
        return set(range(minimum, maximum + 1))
    if token.startswith("*/"):
        step = int(token[2:])
        if step <= 0:
            raise ValueError(f"invalid cron step: {token}")
        return set(range(minimum, maximum + 1, step))

    values: set[int] = set()
    for part in token.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"invalid cron field: {token}")
        if "-" in part:
            left, right = part.split("-", 1)
            start = int(left)
            end = int(right)
            if start > end:
                raise ValueError(f"invalid cron range: {part}")
            for value in range(start, end + 1):
                if value < minimum or value > maximum:
                    raise ValueError(f"cron value out of range: {value}")
                values.add(value)
            continue

        value = int(part)
        if value < minimum or value > maximum:
            raise ValueError(f"cron value out of range: {value}")
        values.add(value)
    return values


def _parse_cron_expr(expr: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron expression must have exactly 5 fields")
    minute = _parse_cron_field(parts[0], 0, 59)
    hour = _parse_cron_field(parts[1], 0, 23)
    day = _parse_cron_field(parts[2], 1, 31)
    month = _parse_cron_field(parts[3], 1, 12)
    weekday = _parse_cron_field(parts[4], 0, 7)
    if 7 in weekday:
        weekday.add(0)
        weekday.remove(7)
    return minute, hour, day, month, weekday


def _matches_cron(expr: str, now: datetime) -> bool:
    minute, hour, day, month, weekday = _parse_cron_expr(expr)
    weekday_now = now.isoweekday() % 7
    return (
        now.minute in minute
        and now.hour in hour
        and now.day in day
        and now.month in month
        and weekday_now in weekday
    )


def run_once(
    *,
    data_dir: str = "data",
    config_file: str | None = None,
    force_enable: bool = False,
    renew_before_days: int | None = None,
) -> int:
    runtime = create_runtime(data_dir=data_dir, config_file=config_file)
    if runtime.config.server is None:
        raise ValueError("scheduler requires [server] configuration block")

    scheduler_cfg = runtime.config.scheduler
    if not scheduler_cfg.enabled and not force_enable:
        typer.echo("scheduler disabled (set [scheduler].enabled=true or --force-enable)")
        return 0

    renew_days = renew_before_days if renew_before_days is not None else scheduler_cfg.renew_before_days
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    created_jobs = schedule_due_renewals(db_path=db_path, renew_before_days=renew_days)
    typer.echo(f"scheduled={len(created_jobs)} renew_before_days={renew_days}")
    return len(created_jobs)


@app.command("run")
def run(
    data_dir: str = typer.Option("data", "--data-dir", "-D", envvar="CERTMAN_DATA_DIR"),
    config_file: str | None = typer.Option(None, "--config-file", "-c", envvar="CERTMAN_CONFIG_FILE"),
    once: bool = typer.Option(False, "--once/--loop"),
    force_enable: bool = typer.Option(False, "--force-enable"),
    renew_before_days: int | None = typer.Option(None, "--renew-before-days"),
    interval_seconds: int | None = typer.Option(None, "--interval-seconds"),
) -> None:
    """Run standalone certificate renewal scheduler."""
    runtime = create_runtime(data_dir=data_dir, config_file=config_file)
    if runtime.config.server is None:
        raise ValueError("scheduler requires [server] configuration block")
    scheduler_cfg = runtime.config.scheduler

    if once:
        run_once(
            data_dir=data_dir,
            config_file=config_file,
            force_enable=force_enable,
            renew_before_days=renew_before_days,
        )
        return

    if not scheduler_cfg.enabled and not force_enable:
        typer.echo("scheduler disabled (set [scheduler].enabled=true or --force-enable)")
        return

    selected_mode = scheduler_cfg.mode
    typer.echo(f"scheduler mode={selected_mode}")
    if selected_mode == "loop":
        sleep_seconds = interval_seconds or scheduler_cfg.scan_interval_seconds
        while True:
            run_once(
                data_dir=data_dir,
                config_file=config_file,
                force_enable=force_enable,
                renew_before_days=renew_before_days,
            )
            time.sleep(max(1, sleep_seconds))
        return

    # cron mode
    cron_expr = scheduler_cfg.cron_expr
    poll_seconds = scheduler_cfg.cron_poll_seconds
    last_trigger_key: str | None = None
    while True:
        now = datetime.now(timezone.utc)
        trigger_key = now.strftime("%Y-%m-%dT%H:%M")
        if trigger_key != last_trigger_key and _matches_cron(cron_expr, now):
            run_once(
                data_dir=data_dir,
                config_file=config_file,
                force_enable=force_enable,
                renew_before_days=renew_before_days,
            )
            last_trigger_key = trigger_key
        time.sleep(max(1, poll_seconds))


@app.command("once")
def once(
    data_dir: str = typer.Option("data", "--data-dir", "-D", envvar="CERTMAN_DATA_DIR"),
    config_file: str | None = typer.Option(None, "--config-file", "-c", envvar="CERTMAN_CONFIG_FILE"),
    force_enable: bool = typer.Option(False, "--force-enable"),
    renew_before_days: int | None = typer.Option(None, "--renew-before-days"),
) -> None:
    """Run exactly one scheduler scan and exit."""
    run_once(
        data_dir=data_dir,
        config_file=config_file,
        force_enable=force_enable,
        renew_before_days=renew_before_days,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
