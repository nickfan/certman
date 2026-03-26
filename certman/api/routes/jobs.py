from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from certman.api.deps import get_job_service
from certman.api.schemas import ApiResponse, ErrorDetail, JobResponse
from certman.services.job_service import JobService

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("", response_model=ApiResponse)
def list_jobs(
    subject_id: Optional[str] = Query(None, description="Filter by subject_id"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
    service: JobService = Depends(get_job_service),
) -> ApiResponse:
    jobs = service.list_jobs(subject_id=subject_id, status=status, limit=limit)
    return ApiResponse(
        success=True,
        data=[JobResponse(**j.model_dump()).model_dump() for j in jobs],
    )


@router.get("/{job_id}", response_model=ApiResponse)
def get_job(job_id: str, service: JobService = Depends(get_job_service)) -> ApiResponse:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=ErrorDetail(code="NOT_FOUND_JOB", message="job not found").model_dump())
    return ApiResponse(success=True, data=JobResponse(**job.model_dump()).model_dump())
