from __future__ import annotations

import typer

from certman.config import create_runtime, resolve_runtime_path
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
) -> None:
    """Run node agent and perform polling."""
    runtime = create_runtime(data_dir=data_dir, config_file=config_file)
    if runtime.config.node_identity is None or runtime.config.control_plane is None:
        raise typer.BadParameter("agent mode requires control_plane and node_identity configuration")

    poller = NodePoller(
        endpoint=runtime.config.control_plane.endpoint,
        node_id=runtime.config.node_identity.node_id,
        private_key_path=resolve_runtime_path(runtime, runtime.config.node_identity.private_key_path),
    )
    assignments = poller.poll()
    typer.echo(f"node_id={runtime.config.node_identity.node_id} poll_count={len(assignments)}")

    if not once:
        typer.echo("loop mode not implemented yet")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
