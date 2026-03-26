from __future__ import annotations

from fastapi import Request

from certman.config import resolve_runtime_path
from certman.events import EventBus
from certman.services.job_service import JobService
from certman.services.webhook_service import WebhookService


def get_job_service(request: Request) -> JobService:
    runtime = request.app.state.runtime
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    return JobService(db_path=db_path)


def get_webhook_service(request: Request) -> WebhookService:
    existing = getattr(request.app.state, "webhook_service", None)
    if existing is not None:
        return existing
    runtime = request.app.state.runtime
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    return WebhookService(db_path=db_path)


def get_event_bus(request: Request) -> EventBus | None:
    return getattr(request.app.state, "event_bus", None)
