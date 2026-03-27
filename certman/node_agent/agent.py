from __future__ import annotations

import os
from pathlib import Path
import time

import typer

from certman.config import create_runtime, resolve_runtime_path
from certman.node_agent.executor import NodeExecutor
from certman.node_agent.poller import NodePoller

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback(invoke_without_command=True)
def run(
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
    once: bool = typer.Option(True, "--once/--loop", help="Run one poll cycle or keep polling"),
    interval_seconds: int | None = typer.Option(None, "--interval-seconds", help="Loop mode interval override"),
) -> None:
    """
    Run node agent and perform certificate job polling.
    
    Startup sequence:
    1. Load config (control_plane endpoint, node_identity)
    2. Initialize poller with registration token from CERTMAN_NODE_REGISTRATION_TOKEN env var
       (Only needed on first startup; agent auto-approves after initial registration)
    3. Attempt registration if needed (if node not yet approved by admin)
    4. Poll server for certificate jobs
    5. Exit with status code:
       - 0: Success (agent ran, registration ok if needed)
       - 2: Registration failed permanently (auth error, invalid key, conflict)
          Action: Check token, public key format, node_id uniqueness
       - 3: Registration failed transiently (network, server error)
          Action: Retry later (k8s restartPolicy will handle)
    
    Output format (for parsing by orchestrators):
      register_status=failed|ok
      register_code=<http-status-or-error-code>
      retryable=true|false
      node_id=<node-id>
      poll_count=<number-of-jobs>
    """
    runtime = create_runtime(data_dir=data_dir, config_file=config_file)
    if runtime.config.node_identity is None or runtime.config.control_plane is None:
        raise typer.BadParameter("agent mode requires control_plane and node_identity configuration")

    poller = NodePoller(
        endpoint=runtime.config.control_plane.endpoint,
        node_id=runtime.config.node_identity.node_id,
        private_key_path=resolve_runtime_path(runtime, runtime.config.node_identity.private_key_path),
        public_key_path=(
            resolve_runtime_path(runtime, runtime.config.node_identity.public_key_path)
            if runtime.config.node_identity.public_key_path
            else None
        ),
        register_token=os.getenv("CERTMAN_NODE_REGISTRATION_TOKEN"),
        encryption_private_key_path=(
            resolve_runtime_path(runtime, runtime.config.node_identity.encryption_private_key_path)
            if runtime.config.node_identity.encryption_private_key_path
            else None
        ),
        encryption_public_key_path=(
            resolve_runtime_path(runtime, runtime.config.node_identity.encryption_public_key_path)
            if runtime.config.node_identity.encryption_public_key_path
            else None
        ),
        prefer_subscribe=runtime.config.control_plane.prefer_subscribe,
        subscribe_wait_seconds=runtime.config.control_plane.subscribe_wait_seconds,
    )

    executor = NodeExecutor()
    poll_interval = interval_seconds or runtime.config.control_plane.poll_interval_seconds

    def _target_dir() -> Path:
        configured = runtime.config.node_identity.certificate_store_path
        if configured:
            return resolve_runtime_path(runtime, configured)
        return runtime.paths.output_dir / runtime.config.node_identity.node_id

    def _default_hooks() -> list[dict]:
        return [hook.model_dump() for hook in runtime.config.hooks]

    def _process_cycle() -> tuple[int, int]:
        assignments = poller.poll()
        processed = 0
        for assignment in assignments:
            job_id = assignment.get("job_id")
            bundle_url = assignment.get("bundle_url")
            bundle_token = assignment.get("bundle_token")
            if not job_id or not bundle_url:
                continue

            bundle_data = poller.fetch_bundle(job_id=job_id, bundle_url=bundle_url, bundle_token=bundle_token)
            if bundle_data is None:
                poller.report_result(job_id=job_id, status="failed", error="bundle download failed")
                processed += 1
                continue

            bundle = bundle_data.get("bundle")
            hooks = bundle_data.get("hooks") or _default_hooks()
            if not isinstance(bundle, dict):
                poller.report_result(job_id=job_id, status="failed", error="bundle payload invalid")
                processed += 1
                continue

            result = executor.execute(
                job_id=job_id,
                bundle=bundle,
                target_dir=_target_dir(),
                hooks=hooks,
            )
            if result.success:
                poller.report_result(job_id=job_id, status="completed", output="ok")
            else:
                poller.report_result(job_id=job_id, status="failed", error=result.error or "execution failed")
            processed += 1

        return len(assignments), processed

    assignments_count, processed_count = _process_cycle()
    registration = poller.last_registration
    if not registration.success:
        typer.echo(
            "register_status=failed "
            f"register_code={registration.code} "
            f"retryable={str(registration.retryable).lower()} "
            f"message={registration.message}"
        )
        raise typer.Exit(code=3 if registration.retryable else 2)

    if os.getenv("CERTMAN_NODE_REGISTRATION_TOKEN"):
        typer.echo(f"register_status=ok register_code={registration.code}")

    typer.echo(
        f"node_id={runtime.config.node_identity.node_id} "
        f"poll_count={assignments_count} processed_count={processed_count}"
    )

    if once:
        return

    while True:
        time.sleep(poll_interval)
        assignments_count, processed_count = _process_cycle()
        typer.echo(
            f"node_id={runtime.config.node_identity.node_id} "
            f"poll_count={assignments_count} processed_count={processed_count}"
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
