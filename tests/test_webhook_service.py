from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from certman.services.webhook_service import WebhookService


def test_webhook_service_creates_subscription_and_delivers_event(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code=200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = WebhookService(db_path=tmp_path / "certman.db", client=client)
    subscription = service.create_subscription(topic="job.completed", endpoint="https://example.test/hook", secret="topsecret")

    deliveries = service.publish_event(topic="job.completed", payload={"job_id": "job-1"})

    assert subscription.subscription_id
    assert len(deliveries) == 1
    assert deliveries[0].status == "delivered"
    assert requests[0].headers["x-certman-signature"]
    assert json.loads(requests[0].content.decode("utf-8"))["payload"]["job_id"] == "job-1"


def test_webhook_service_marks_failed_delivery_for_retry(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, json={"ok": False})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = WebhookService(db_path=tmp_path / "certman.db", client=client)
    service.create_subscription(topic="job.failed", endpoint="https://example.test/hook", secret="topsecret")

    deliveries = service.publish_event(
        topic="job.failed",
        payload={"job_id": "job-1"},
        now=datetime(2026, 3, 26, tzinfo=timezone.utc),
    )

    assert len(deliveries) == 1
    assert deliveries[0].status == "retry"
    assert deliveries[0].attempts == 1
    assert deliveries[0].next_retry_at == datetime(2026, 3, 26, 0, 1, tzinfo=timezone.utc)


def test_webhook_service_marks_transport_failure_for_retry(tmp_path: Path) -> None:
    def handler(request: httpx.Request):
        raise httpx.ConnectError("connect failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = WebhookService(db_path=tmp_path / "certman.db", client=client)
    service.create_subscription(topic="job.failed", endpoint="https://example.test/hook", secret="topsecret")

    deliveries = service.publish_event(
        topic="job.failed",
        payload={"job_id": "job-1"},
        now=datetime(2026, 3, 26, tzinfo=timezone.utc),
    )

    assert len(deliveries) == 1
    assert deliveries[0].status == "retry"
    assert deliveries[0].http_status is None
    assert "connect failed" in (deliveries[0].error or "")


def test_webhook_service_rotates_secret_for_existing_subscription(tmp_path: Path) -> None:
    service = WebhookService(db_path=tmp_path / "certman.db")
    first = service.create_subscription(topic="job.completed", endpoint="https://example.test/hook", secret="old")
    second = service.create_subscription(topic="job.completed", endpoint="https://example.test/hook", secret="new")

    assert first.subscription_id == second.subscription_id
    assert second.secret == "new"