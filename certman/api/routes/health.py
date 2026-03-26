from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Check service health",
    description="Lightweight health probe used by operators, load balancers, and automation. This endpoint intentionally returns a bare response instead of the ApiResponse envelope.",
    response_description="Bare status response indicating the process is healthy",
)
def health() -> dict[str, str]:
    return {"status": "ok"}
