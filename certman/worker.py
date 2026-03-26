from __future__ import annotations

import typer

from certman.config import create_runtime, resolve_runtime_path
from certman.events import EventBus
from certman.services.cert_service import CertService
from certman.services.job_service import JobService

app = typer.Typer(add_completion=False)


def run_once(*, data_dir: str = "data", config_file: str | None = None, event_bus: EventBus | None = None) -> int:
    runtime = create_runtime(data_dir=data_dir, config_file=config_file)
    if runtime.config.server is None:
        raise ValueError("server mode requires [server] configuration block")

    service = JobService(db_path=resolve_runtime_path(runtime, runtime.config.server.db_path))
    job = service.claim_next_job()
    if job is None:
        return 0

    cert_service = CertService(runtime)
    try:
        if job.job_type == "issue":
            result = cert_service.issue(job.subject_id)
            if result.success:
                updated = service.update_status(job.job_id, status="completed", result="ok")
                if event_bus is not None and updated is not None:
                    event_bus.publish("job.completed", updated.model_dump())
            else:
                updated = service.update_status(job.job_id, status="failed", error=result.error)
                if event_bus is not None and updated is not None:
                    event_bus.publish("job.failed", updated.model_dump())
        elif job.job_type == "renew":
            results = cert_service.renew(name=job.subject_id)
            error_messages = [result.error for result in results if not result.success]
            if error_messages:
                updated = service.update_status(job.job_id, status="failed", error="; ".join(filter(None, error_messages)))
                if event_bus is not None and updated is not None:
                    event_bus.publish("job.failed", updated.model_dump())
            else:
                updated = service.update_status(job.job_id, status="completed", result="ok")
                if event_bus is not None and updated is not None:
                    event_bus.publish("job.completed", updated.model_dump())
        else:
            updated = service.update_status(job.job_id, status="failed", error=f"unsupported job_type: {job.job_type}")
            if event_bus is not None and updated is not None:
                event_bus.publish("job.failed", updated.model_dump())
    except Exception as exc:
        updated = service.update_status(job.job_id, status="failed", error=str(exc))
        if event_bus is not None and updated is not None:
            event_bus.publish("job.failed", updated.model_dump())

    return 1


@app.command("run")
def run(
    data_dir: str = typer.Option("data", "--data-dir", "-D", envvar="CERTMAN_DATA_DIR"),
    config_file: str | None = typer.Option(None, "--config-file", "-c", envvar="CERTMAN_CONFIG_FILE"),
    once: bool = typer.Option(True, "--once/--loop"),
    interval_seconds: int = typer.Option(30, "--interval-seconds"),
) -> None:
    """Run background worker once or in loop mode."""
    if once:
        processed = run_once(data_dir=data_dir, config_file=config_file)
        typer.echo(f"processed={processed}")
        return

    import time

    while True:
        processed = run_once(data_dir=data_dir, config_file=config_file)
        typer.echo(f"processed={processed}")
        time.sleep(interval_seconds)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
