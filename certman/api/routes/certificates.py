from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from certman.api.deps import get_event_bus, get_job_service
from certman.api.schemas import ApiResponse, IssueCertRequest
from certman.events import EventBus
from certman.services.job_service import JobService

router = APIRouter(prefix="/api/v1/certificates", tags=["certificates"])


@router.post("", response_model=ApiResponse, status_code=status.HTTP_202_ACCEPTED)
def issue_certificate(
    payload: IssueCertRequest,
    http_request: Request,
    service: JobService = Depends(get_job_service),
    event_bus: EventBus | None = Depends(get_event_bus),
) -> ApiResponse:
    if not payload.entry_name:
        raise HTTPException(status_code=400, detail={"code": "INVALID_ENTRY", "message": "entry_name is required"})
    runtime = http_request.app.state.runtime
    if not any(entry.name == payload.entry_name for entry in runtime.config.entries):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_ENTRY", "message": "entry not found"})

    job = service.create_job(job_type="issue", subject_id=payload.entry_name)
    if event_bus is not None:
        event_bus.publish("job.queued", job.model_dump())
    return ApiResponse(success=True, data={"job_id": job.job_id})
