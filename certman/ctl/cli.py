from __future__ import annotations

import time
from dataclasses import dataclass
import json
from typing import Any, Optional

import httpx
import typer


EXIT_NETWORK_ERROR = 3
EXIT_API_ERROR = 4

app = typer.Typer(add_completion=False)
cert_app = typer.Typer(add_completion=False)
job_app = typer.Typer(add_completion=False)
webhook_app = typer.Typer(add_completion=False)
app.add_typer(cert_app, name="cert")
app.add_typer(job_app, name="job")
app.add_typer(webhook_app, name="webhook")


@dataclass(frozen=True)
class CtlOptions:
    endpoint: str
    timeout: float
    output: str
    token: str | None


def _ctx_options(ctx: typer.Context) -> CtlOptions:
    return ctx.obj


@app.callback()
def _callback(
    ctx: typer.Context,
    endpoint: str = typer.Option(
        "http://127.0.0.1:8000",
        "--endpoint",
        help="Control plane API endpoint",
        envvar="CERTMAN_SERVER_ENDPOINT",
    ),
    timeout: float = typer.Option(10.0, "--timeout", help="HTTP timeout in seconds"),
    output: str = typer.Option("text", "--output", help="Output format: text|json"),
    token: str | None = typer.Option(None, "--token", help="Bearer token", envvar="CERTMAN_SERVER_TOKEN"),
) -> None:
    if output not in {"text", "json"}:
        raise typer.BadParameter("output must be text or json")
    ctx.obj = CtlOptions(endpoint=endpoint.rstrip("/"), timeout=timeout, output=output, token=token)


def _call_api(
    *,
    method: str,
    path: str,
    endpoint: str,
    timeout: float,
    token: str | None,
    payload: dict[str, Any] | None = None,
) -> Any:
    headers: dict[str, str] = {}
    if token:
        headers = {"Authorization": f"Bearer {token}"}

    url = f"{endpoint}{path}"
    try:
        response = httpx.request(method=method, url=url, json=payload, timeout=timeout, headers=headers)
    except httpx.RequestError as exc:
        raise ConnectionError(f"NETWORK_ERROR:{exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("API_ERROR:INVALID_JSON:server returned non-json response") from exc

    if isinstance(body, dict) and "success" in body:
        if body.get("success"):
            return body.get("data")

        error = body.get("error") or {}
        code = error.get("code", "API_ERROR")
        message = error.get("message", f"http status {response.status_code}")
        raise RuntimeError(f"API_ERROR:{code}:{message}")

    if response.status_code >= 400:
        raise RuntimeError(f"API_ERROR:HTTP_{response.status_code}:request failed")

    return body


def _emit_result(result: Any, output: str) -> None:
    if output == "json":
        typer.echo(json.dumps(result, ensure_ascii=False))
        return

    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                typer.echo(" ".join(f"{k}={v}" for k, v in item.items()))
            else:
                typer.echo(str(item))
        return

    if isinstance(result, dict):
        rendered = " ".join(f"{key}={value}" for key, value in result.items())
        typer.echo(rendered)
        return

    typer.echo(str(result))


def _run_or_exit(ctx: typer.Context, *, method: str, path: str, payload: dict[str, Any] | None = None) -> None:
    options = _ctx_options(ctx)
    try:
        result = _call_api(
            method=method,
            path=path,
            endpoint=options.endpoint,
            timeout=options.timeout,
            token=options.token,
            payload=payload,
        )
    except ConnectionError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=EXIT_API_ERROR) from exc

    _emit_result(result, options.output)


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

@app.command("health")
def health(ctx: typer.Context) -> None:
    """Check control plane health."""
    _run_or_exit(ctx, method="GET", path="/health")


# ---------------------------------------------------------------------------
# cert commands
# ---------------------------------------------------------------------------

@cert_app.command("create")
def cert_create(
    ctx: typer.Context,
    entry_name: str = typer.Option(..., "--entry-name", "-n", help="Entry name"),
) -> None:
    """Create a certificate issuance job."""
    _run_or_exit(
        ctx,
        method="POST",
        path="/api/v1/certificates",
        payload={"entry_name": entry_name},
    )


@cert_app.command("list")
def cert_list(ctx: typer.Context) -> None:
    """List all certificate jobs."""
    _run_or_exit(ctx, method="GET", path="/api/v1/certificates")


@cert_app.command("get")
def cert_get(
    ctx: typer.Context,
    entry_name: str = typer.Option(..., "--entry-name", "-n", help="Entry name"),
) -> None:
    """Get jobs for a specific certificate entry."""
    _run_or_exit(ctx, method="GET", path=f"/api/v1/certificates/{entry_name}")


@cert_app.command("renew")
def cert_renew(
    ctx: typer.Context,
    entry_name: str = typer.Option(..., "--entry-name", "-n", help="Entry name"),
) -> None:
    """Enqueue a renewal job for the given entry (idempotent)."""
    _run_or_exit(ctx, method="POST", path=f"/api/v1/certificates/{entry_name}/renew")


# ---------------------------------------------------------------------------
# job commands
# ---------------------------------------------------------------------------

@job_app.command("get")
def job_get(
    ctx: typer.Context,
    job_id: str = typer.Option(..., "--job-id", help="Job ID"),
) -> None:
    """Get job details by id."""
    _run_or_exit(ctx, method="GET", path=f"/api/v1/jobs/{job_id}")


@job_app.command("list")
def job_list(
    ctx: typer.Context,
    subject_id: Optional[str] = typer.Option(None, "--subject-id", help="Filter by subject_id"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    limit: int = typer.Option(50, "--limit", help="Max results"),
) -> None:
    """List jobs with optional filters."""
    path = "/api/v1/jobs"
    params: list[str] = []
    if subject_id:
        params.append(f"subject_id={subject_id}")
    if status:
        params.append(f"status={status}")
    params.append(f"limit={limit}")
    path = path + "?" + "&".join(params)
    _run_or_exit(ctx, method="GET", path=path)


@job_app.command("wait")
def job_wait(
    ctx: typer.Context,
    job_id: str = typer.Option(..., "--job-id", help="Job ID"),
    poll_interval: float = typer.Option(3.0, "--poll-interval", help="Poll interval in seconds"),
    max_wait: float = typer.Option(120.0, "--max-wait", help="Maximum wait time in seconds"),
) -> None:
    """Poll a job until it reaches a terminal state (completed/failed/cancelled)."""
    options = _ctx_options(ctx)
    terminal = {"completed", "failed", "cancelled"}
    deadline = time.monotonic() + max_wait

    while True:
        try:
            result = _call_api(
                method="GET",
                path=f"/api/v1/jobs/{job_id}",
                endpoint=options.endpoint,
                timeout=options.timeout,
                token=options.token,
            )
        except ConnectionError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=EXIT_NETWORK_ERROR) from exc
        except RuntimeError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=EXIT_API_ERROR) from exc

        if isinstance(result, dict):
            current_status = result.get("status", "")
            if current_status in terminal:
                _emit_result(result, options.output)
                if current_status == "failed":
                    raise typer.Exit(code=1)
                return

        if time.monotonic() >= deadline:
            typer.echo(f"TIMEOUT: job {job_id} did not reach terminal state within {max_wait}s")
            raise typer.Exit(code=1)

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# webhook commands
# ---------------------------------------------------------------------------

@webhook_app.command("create")
def webhook_create(
    ctx: typer.Context,
    topic: str = typer.Option(..., "--topic", help="Webhook topic"),
    endpoint_url: str = typer.Option(..., "--endpoint-url", help="Webhook target URL"),
    secret: str = typer.Option(..., "--secret", help="Webhook secret"),
) -> None:
    """Create webhook subscription."""
    _run_or_exit(
        ctx,
        method="POST",
        path="/api/v1/webhooks",
        payload={"topic": topic, "endpoint": endpoint_url, "secret": secret},
    )


@webhook_app.command("list")
def webhook_list(
    ctx: typer.Context,
    topic: Optional[str] = typer.Option(None, "--topic", help="Filter by topic"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
) -> None:
    """List webhook subscriptions."""
    path = "/api/v1/webhooks"
    params: list[str] = []
    if topic:
        params.append(f"topic={topic}")
    if status:
        params.append(f"status={status}")
    if params:
        path = path + "?" + "&".join(params)
    _run_or_exit(ctx, method="GET", path=path)


@webhook_app.command("get")
def webhook_get(
    ctx: typer.Context,
    subscription_id: str = typer.Option(..., "--id", help="Subscription ID"),
) -> None:
    """Get a webhook subscription by id."""
    _run_or_exit(ctx, method="GET", path=f"/api/v1/webhooks/{subscription_id}")


@webhook_app.command("update")
def webhook_update(
    ctx: typer.Context,
    subscription_id: str = typer.Option(..., "--id", help="Subscription ID"),
    endpoint_url: Optional[str] = typer.Option(None, "--endpoint-url", help="New endpoint URL"),
    secret: Optional[str] = typer.Option(None, "--secret", help="New secret"),
    status: Optional[str] = typer.Option(None, "--status", help="New status (active/inactive)"),
) -> None:
    """Update a webhook subscription."""
    payload: dict[str, Any] = {}
    if endpoint_url is not None:
        payload["endpoint"] = endpoint_url
    if secret is not None:
        payload["secret"] = secret
    if status is not None:
        payload["status"] = status
    if not payload:
        typer.echo("Nothing to update — provide at least one of --endpoint-url, --secret, --status")
        raise typer.Exit(code=1)
    _run_or_exit(ctx, method="PUT", path=f"/api/v1/webhooks/{subscription_id}", payload=payload)


@webhook_app.command("delete")
def webhook_delete(
    ctx: typer.Context,
    subscription_id: str = typer.Option(..., "--id", help="Subscription ID"),
) -> None:
    """Delete a webhook subscription."""
    _run_or_exit(ctx, method="DELETE", path=f"/api/v1/webhooks/{subscription_id}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
