from __future__ import annotations

import typer
import uvicorn

from certman.api.app import create_app

app = typer.Typer(add_completion=False)


def create_application(*, data_dir: str = "data", config_file: str | None = None):
    return create_app(data_dir=data_dir, config_file=config_file)


@app.command("run")
def run(
    data_dir: str = typer.Option("data", "--data-dir", "-D", envvar="CERTMAN_DATA_DIR"),
    config_file: str | None = typer.Option(None, "--config-file", "-c", envvar="CERTMAN_CONFIG_FILE"),
) -> None:
    """Run control plane HTTP server."""
    application = create_application(data_dir=data_dir, config_file=config_file)
    runtime = application.state.runtime
    uvicorn.run(
        application,
        host=runtime.config.server.listen_host,
        port=runtime.config.server.listen_port,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
