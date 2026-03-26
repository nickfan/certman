from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from certman.api.deps import get_event_bus, get_job_service
from certman.api.schemas import ApiResponse, IssueCertRequest, JobAcceptedResponse, JobResponse, RenewJobAcceptedResponse
from certman.events import EventBus
from certman.services.job_service import JobService

router = APIRouter(prefix="/api/v1/certificates", tags=["certificates"])


@router.get(
    "",
    response_model=ApiResponse[list[JobResponse]],
    summary="List certificate jobs",
    description="Return recent certificate-related jobs, including both issue and renew job types.",
    response_description="Recent issue and renew jobs",
)
def list_certificates(
    service: JobService = Depends(get_job_service),
) -> ApiResponse[list[JobResponse]]:
    """List all certificate jobs (issue + renew)."""
    jobs = service.list_jobs(limit=200)
    cert_jobs = [j for j in jobs if j.job_type in ("issue", "renew")]
    return ApiResponse(
        success=True,
        data=[JobResponse(**j.model_dump()) for j in cert_jobs],
    )


@router.get(
    "/{entry_name}",
    response_model=ApiResponse[list[JobResponse]],
    summary="List jobs for one certificate entry",
    description="Return issue and renew jobs belonging to a specific configured certificate entry.",
    response_description="Jobs associated with the requested certificate entry",
    responses={404: {"description": "Certificate entry not found"}},
)
def get_certificate_jobs(
    entry_name: str,
    http_request: Request,
    service: JobService = Depends(get_job_service),
) -> ApiResponse[list[JobResponse]]:
    """List jobs for a specific certificate entry."""
    runtime = http_request.app.state.runtime
    if not any(entry.name == entry_name for entry in runtime.config.entries):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_ENTRY", "message": "entry not found"})
    jobs = service.list_jobs(subject_id=entry_name, limit=50)
    return ApiResponse(
        success=True,
        data=[JobResponse(**j.model_dump()) for j in jobs],
    )


@router.post(
    "",
    response_model=ApiResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create issue job",
    description="Submit a new certificate issuance job for a configured entry.",
    response_description="Accepted issue job identifier",
    responses={404: {"description": "Certificate entry not found"}},
)
def issue_certificate(
    payload: IssueCertRequest,
    http_request: Request,
    service: JobService = Depends(get_job_service),
    event_bus: EventBus | None = Depends(get_event_bus),
) -> ApiResponse[JobAcceptedResponse]:
    if not payload.entry_name:
        raise HTTPException(status_code=400, detail={"code": "INVALID_ENTRY", "message": "entry_name is required"})
    runtime = http_request.app.state.runtime
    if not any(entry.name == payload.entry_name for entry in runtime.config.entries):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_ENTRY", "message": "entry not found"})

    job = service.create_job(job_type="issue", subject_id=payload.entry_name)
    if event_bus is not None:
        event_bus.publish("job.queued", job.model_dump())
    return ApiResponse(success=True, data=JobAcceptedResponse(job_id=job.job_id))


@router.post(
    "/{entry_name}/renew",
    response_model=ApiResponse[RenewJobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create or reuse renew job",
    description="Submit a renewal job for an entry. If a queued renew job already exists for the same subject, the existing job is returned and `created=false`.",
    response_description="Accepted renew job identifier and dedupe result",
    responses={404: {"description": "Certificate entry not found"}},
)
def renew_certificate(
    entry_name: str,
    http_request: Request,
    service: JobService = Depends(get_job_service),
    event_bus: EventBus | None = Depends(get_event_bus),
) -> ApiResponse[RenewJobAcceptedResponse]:
    """Enqueue a renewal job for the given entry (idempotent)."""
    runtime = http_request.app.state.runtime
    if not any(entry.name == entry_name for entry in runtime.config.entries):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_ENTRY", "message": "entry not found"})

    job, created = service.enqueue_unique_job(job_type="renew", subject_id=entry_name)
    if event_bus is not None and created:
        event_bus.publish("job.queued", job.model_dump())
    return ApiResponse(success=True, data=RenewJobAcceptedResponse(job_id=job.job_id, created=created))
