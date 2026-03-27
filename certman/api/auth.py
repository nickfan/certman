from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status


def _get_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _resolve_entry_token(request: Request, entry_name: str) -> str | None:
    runtime = request.app.state.runtime
    entry = next((item for item in runtime.config.entries if item.name == entry_name), None)
    if entry is not None and entry.token:
        return entry.token
    return runtime.config.global_.token


def _is_token_auth_enabled(request: Request) -> bool:
    runtime = request.app.state.runtime
    server = runtime.config.server
    return bool(server and server.token_auth_enabled)


def _raise_token_config_error() -> None:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "code": "AUTH_TOKEN_CONFIG_ERROR",
            "message": "token auth is enabled but no effective token is configured",
        },
    )


def _require_token(request: Request, expected_token: str) -> None:
    provided = _get_bearer_token(request)
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_MISSING_TOKEN", "message": "missing bearer token"},
        )
    if not hmac.compare_digest(provided, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID_TOKEN", "message": "invalid bearer token"},
        )


def require_global_token_if_configured(request: Request) -> None:
    if not _is_token_auth_enabled(request):
        return

    expected = request.app.state.runtime.config.global_.token
    if not expected:
        _raise_token_config_error()
    _require_token(request, expected)


def require_entry_token_if_configured(request: Request, entry_name: str) -> None:
    if not _is_token_auth_enabled(request):
        return

    expected = _resolve_entry_token(request, entry_name)
    if not expected:
        _raise_token_config_error()
    _require_token(request, expected)
