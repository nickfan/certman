from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from certman.api.auth import require_global_token_if_configured
from certman.api.schemas import ApiResponse, ConfigEntryResponse, ConfigValidateRequest, ConfigValidateResponse

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get(
    "/entries",
    response_model=ApiResponse[list[ConfigEntryResponse]],
    summary="List merged config entries",
)
def list_entries(http_request: Request) -> ApiResponse[list[ConfigEntryResponse]]:
    require_global_token_if_configured(http_request)
    runtime = http_request.app.state.runtime
    return ApiResponse(
        success=True,
        data=[ConfigEntryResponse(**entry.model_dump()) for entry in runtime.config.entries],
    )


@router.get(
    "/entries/{entry_name}",
    response_model=ApiResponse[ConfigEntryResponse],
    summary="Get one merged config entry",
    responses={404: {"description": "Entry not found"}},
)
def get_entry(entry_name: str, http_request: Request) -> ApiResponse[ConfigEntryResponse]:
    require_global_token_if_configured(http_request)
    runtime = http_request.app.state.runtime
    entry = next((entry for entry in runtime.config.entries if entry.name == entry_name), None)
    if entry is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_ENTRY", "message": "entry not found"})
    return ApiResponse(success=True, data=ConfigEntryResponse(**entry.model_dump()))


@router.post(
    "/validate",
    response_model=ApiResponse[ConfigValidateResponse],
    summary="Validate required secrets for selected entries",
)
def validate_config(payload: ConfigValidateRequest, http_request: Request) -> ApiResponse[ConfigValidateResponse]:
    require_global_token_if_configured(http_request)
    runtime = http_request.app.state.runtime
    try:
        runtime.config.validate_required_secrets(
            runtime.env,
            entry_names=payload.entry_names,
            validate_all=payload.validate_all,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CONFIG", "message": str(exc)}) from exc
    return ApiResponse(success=True, data=ConfigValidateResponse(ok=True))
