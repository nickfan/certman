from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from certman.api.deps import get_webhook_service
from certman.api.schemas import ApiResponse, DeleteResponse, UpdateWebhookRequest, WebhookCreatedResponse, WebhookResponse, WebhookSubscriptionRequest
from certman.services.webhook_service import WebhookService

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _format_subscription(s) -> WebhookResponse:
    return WebhookResponse(
        id=s.subscription_id,
        topic=s.topic,
        endpoint=s.endpoint,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get(
    "",
    response_model=ApiResponse[list[WebhookResponse]],
    summary="List webhook subscriptions",
    description="List webhook subscriptions with optional filtering by topic and status.",
    response_description="Webhook subscription list",
)
def list_webhook_subscriptions(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    sub_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    service: WebhookService = Depends(get_webhook_service),
) -> ApiResponse[list[WebhookResponse]]:
    subscriptions = service.list_subscriptions(topic=topic, status=sub_status)
    return ApiResponse(success=True, data=[_format_subscription(s) for s in subscriptions])


@router.get(
    "/{subscription_id}",
    response_model=ApiResponse[WebhookResponse],
    summary="Get webhook subscription",
    description="Fetch a webhook subscription by identifier.",
    response_description="Requested webhook subscription",
    responses={404: {"description": "Webhook subscription not found"}},
)
def get_webhook_subscription(
    subscription_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> ApiResponse[WebhookResponse]:
    sub = service.get_subscription(subscription_id)
    if sub is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND_WEBHOOK", "message": "webhook subscription not found"},
        )
    return ApiResponse(success=True, data=_format_subscription(sub))


@router.post(
    "",
    response_model=ApiResponse[WebhookCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create webhook subscription",
    description="Create a new webhook subscription. If the same topic + endpoint already exists, its secret is refreshed and the existing subscription is reused.",
    response_description="Created or updated webhook subscription identifier",
)
def create_webhook_subscription(
    request: WebhookSubscriptionRequest,
    service: WebhookService = Depends(get_webhook_service),
) -> ApiResponse[WebhookCreatedResponse]:
    try:
        subscription = service.create_subscription(
            topic=request.topic,
            endpoint=request.endpoint,
            secret=request.secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_WEBHOOK", "message": str(exc)}) from exc
    return ApiResponse(success=True, data=WebhookCreatedResponse(id=subscription.subscription_id))


@router.put(
    "/{subscription_id}",
    response_model=ApiResponse[WebhookResponse],
    summary="Update webhook subscription",
    description="Update webhook endpoint, shared secret, or status.",
    response_description="Updated webhook subscription",
    responses={404: {"description": "Webhook subscription not found"}},
)
def update_webhook_subscription(
    subscription_id: str,
    request: UpdateWebhookRequest,
    service: WebhookService = Depends(get_webhook_service),
) -> ApiResponse[WebhookResponse]:
    try:
        updated = service.update_subscription(
            subscription_id,
            endpoint=request.endpoint,
            secret=request.secret,
            status=request.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_WEBHOOK", "message": str(exc)}) from exc
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND_WEBHOOK", "message": "webhook subscription not found"},
        )
    return ApiResponse(success=True, data=_format_subscription(updated))


@router.delete(
    "/{subscription_id}",
    response_model=ApiResponse[DeleteResponse],
    summary="Delete webhook subscription",
    description="Delete a webhook subscription by identifier.",
    response_description="Deletion result",
    responses={404: {"description": "Webhook subscription not found"}},
)
def delete_webhook_subscription(
    subscription_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> ApiResponse[DeleteResponse]:
    deleted = service.delete_subscription(subscription_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND_WEBHOOK", "message": "webhook subscription not found"},
        )
    return ApiResponse(success=True, data=DeleteResponse(deleted=True))