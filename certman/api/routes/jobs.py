from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from certman.api.auth import require_entry_token_if_configured, require_global_token_if_configured
from certman.api.deps import get_job_service
from certman.api.schemas import ApiResponse, ErrorDetail, JobResponse
from certman.services.job_service import JobService

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get(
    "",
    response_model=ApiResponse[list[JobResponse]],
    summary="List jobs",
    description="List recent jobs with optional filters on subject_id and status.",
    response_description="Filtered job list",
)
def list_jobs(
    http_request: Request,
    subject_id: Optional[str] = Query(None, description="Filter by subject_id"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
    service: JobService = Depends(get_job_service),
) -> ApiResponse[list[JobResponse]]:
    if subject_id:
        require_entry_token_if_configured(http_request, subject_id)
    else:
        require_global_token_if_configured(http_request)
    jobs = service.list_jobs(subject_id=subject_id, status=status, limit=limit)
    return ApiResponse(
        success=True,
        data=[JobResponse(**j.model_dump()) for j in jobs],
    )


@router.get(
    "/{job_id}",
    response_model=ApiResponse[JobResponse],
    summary="Get one job",
    description="Fetch the latest persisted state for a specific job.",
    response_description="Requested job record",
    responses={404: {"description": "Job not found"}},
)
def get_job(job_id: str, request: Request, service: JobService = Depends(get_job_service)) -> ApiResponse[JobResponse]:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=ErrorDetail(code="NOT_FOUND_JOB", message="job not found").model_dump())
    require_entry_token_if_configured(request, job.subject_id)
    return ApiResponse(success=True, data=JobResponse(**job.model_dump()))
