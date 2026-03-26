from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from certman.api.deps import get_webhook_service
from certman.api.schemas import ApiResponse, WebhookSubscriptionRequest
from certman.services.webhook_service import WebhookService

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
def create_webhook_subscription(
    request: WebhookSubscriptionRequest,
    service: WebhookService = Depends(get_webhook_service),
) -> ApiResponse:
    try:
        subscription = service.create_subscription(
            topic=request.topic,
            endpoint=request.endpoint,
            secret=request.secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_WEBHOOK", "message": str(exc)}) from exc
    return ApiResponse(success=True, data={"id": subscription.subscription_id})