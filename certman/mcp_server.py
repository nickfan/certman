from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class McpServerConfig:
    endpoint: str
    timeout: float
    token: str | None
    poll_interval: float
    max_wait: float


def _parse_api_response(*, status_code: int, body: Any) -> Any:
    if isinstance(body, dict) and "success" in body:
        if body.get("success"):
            return body.get("data")
        error = body.get("error") or {}
        code = error.get("code", "API_ERROR")
        message = error.get("message", f"http status {status_code}")
        raise RuntimeError(f"API_ERROR:{code}:{message}")
    if status_code >= 400:
        raise RuntimeError(f"API_ERROR:HTTP_{status_code}:request failed")
    return body


def _call_api(
    *,
    method: str,
    path: str,
    config: McpServerConfig,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    headers: dict[str, str] = {}
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"

    url = f"{config.endpoint}{path}"
    try:
        response = httpx.request(
            method=method,
            url=url,
            json=payload,
            params=params,
            timeout=config.timeout,
            headers=headers,
        )
    except httpx.RequestError as exc:
        raise ConnectionError(f"NETWORK_ERROR:{exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("API_ERROR:INVALID_JSON:server returned non-json response") from exc

    return _parse_api_response(status_code=response.status_code, body=body)


def _path_segment(value: str) -> str:
    return quote(value, safe="")


def create_mcp_server(config: McpServerConfig):
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("certman-control-plane")

    @mcp.tool()
    def health() -> dict[str, Any]:
        """Check control-plane health status."""
        return _call_api(method="GET", path="/health", config=config)

    @mcp.tool()
    def cert_create(entry_name: str) -> dict[str, Any]:
        """Submit an async certificate issuance job for one entry.

        Returns a job_id. Use job_wait to wait for terminal status.
        """
        return _call_api(
            method="POST",
            path="/api/v1/certificates",
            payload={"entry_name": entry_name},
            config=config,
        )

    @mcp.tool()
    def cert_list() -> list[dict[str, Any]]:
        """List recent certificate-related jobs."""
        return _call_api(method="GET", path="/api/v1/certificates", config=config)

    @mcp.tool()
    def cert_get(entry_name: str) -> list[dict[str, Any]]:
        """List jobs for a specific certificate entry."""
        return _call_api(method="GET", path=f"/api/v1/certificates/{_path_segment(entry_name)}", config=config)

    @mcp.tool()
    def cert_renew(entry_name: str) -> dict[str, Any]:
        """Create or reuse an async renewal job for one entry.

        Returns a job_id. Use job_wait to wait for terminal status.
        """
        return _call_api(method="POST", path=f"/api/v1/certificates/{_path_segment(entry_name)}/renew", config=config)

    @mcp.tool()
    def job_get(job_id: str) -> dict[str, Any]:
        """Get one job by job id."""
        return _call_api(method="GET", path=f"/api/v1/jobs/{_path_segment(job_id)}", config=config)

    @mcp.tool()
    def job_list(
        subject_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List jobs with optional filters."""
        params: dict[str, Any] = {"limit": limit}
        if subject_id:
            params["subject_id"] = subject_id
        if status:
            params["status"] = status
        return _call_api(method="GET", path="/api/v1/jobs", params=params, config=config)

    @mcp.tool()
    def job_wait(job_id: str) -> dict[str, Any]:
        """Poll a job until completed, failed, or cancelled.

        Intended to be paired with cert_create and cert_renew.
        """
        deadline = time.monotonic() + config.max_wait
        terminal = {"completed", "failed", "cancelled"}

        while True:
            result = _call_api(method="GET", path=f"/api/v1/jobs/{_path_segment(job_id)}", config=config)
            if isinstance(result, dict) and result.get("status") in terminal:
                return result
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"API_ERROR:TIMEOUT:job {job_id} did not reach terminal state within {config.max_wait}s"
                )
            time.sleep(config.poll_interval)

    @mcp.tool()
    def webhook_create(topic: str, endpoint_url: str, secret: str) -> dict[str, Any]:
        """Create one webhook subscription."""
        return _call_api(
            method="POST",
            path="/api/v1/webhooks",
            payload={"topic": topic, "endpoint": endpoint_url, "secret": secret},
            config=config,
        )

    @mcp.tool()
    def webhook_list(topic: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """List webhook subscriptions with optional filters."""
        params: dict[str, Any] = {}
        if topic:
            params["topic"] = topic
        if status:
            params["status"] = status
        return _call_api(method="GET", path="/api/v1/webhooks", params=params or None, config=config)

    @mcp.tool()
    def webhook_get(subscription_id: str) -> dict[str, Any]:
        """Get one webhook subscription."""
        return _call_api(method="GET", path=f"/api/v1/webhooks/{_path_segment(subscription_id)}", config=config)

    @mcp.tool()
    def webhook_update(
        subscription_id: str,
        endpoint_url: str | None = None,
        secret: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Update a webhook subscription."""
        payload: dict[str, Any] = {}
        if endpoint_url is not None:
            payload["endpoint"] = endpoint_url
        if secret is not None:
            payload["secret"] = secret
        if status is not None:
            payload["status"] = status
        if not payload:
            raise ValueError("At least one of endpoint_url, secret, status must be provided")
        return _call_api(
            method="PUT",
            path=f"/api/v1/webhooks/{_path_segment(subscription_id)}",
            payload=payload,
            config=config,
        )

    @mcp.tool()
    def webhook_delete(subscription_id: str) -> dict[str, Any]:
        """Delete one webhook subscription."""
        return _call_api(method="DELETE", path=f"/api/v1/webhooks/{_path_segment(subscription_id)}", config=config)

    return mcp


def _parse_args() -> McpServerConfig:
    parser = argparse.ArgumentParser(description="CertMan MCP server")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000", help="Control-plane endpoint")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument("--token", default=None, help="Optional bearer token (fallback to CERTMAN_MCP_TOKEN)")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="job_wait poll interval in seconds")
    parser.add_argument("--max-wait", type=float, default=120.0, help="job_wait max wait seconds")
    args = parser.parse_args()
    return McpServerConfig(
        endpoint=args.endpoint.rstrip("/"),
        timeout=args.timeout,
        token=args.token if args.token is not None else os.getenv("CERTMAN_MCP_TOKEN"),
        poll_interval=args.poll_interval,
        max_wait=args.max_wait,
    )


def main() -> None:
    config = _parse_args()
    mcp = create_mcp_server(config)
    mcp.run()


if __name__ == "__main__":
    main()
