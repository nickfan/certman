from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from certman.db.engine import make_engine, make_session_factory
from certman.db.models import Base, WebhookDeliveryORM, WebhookSubscriptionORM


@dataclass(frozen=True)
class WebhookSubscriptionRecord:
    subscription_id: str
    topic: str
    endpoint: str
    secret: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WebhookDeliveryRecord:
    delivery_id: str
    subscription_id: str
    topic: str
    status: str
    attempts: int
    http_status: int | None
    error: str | None
    next_retry_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WebhookService:
    def __init__(
        self,
        *,
        db_path: str | Path,
        client: httpx.Client | None = None,
        retry_delay_seconds: int = 60,
    ) -> None:
        self._db_path = Path(db_path)
        self._engine = make_engine(self._db_path)
        Base.metadata.create_all(self._engine)
        self._session_factory = make_session_factory(self._db_path)
        self._client = client or httpx.Client()
        self._retry_delay_seconds = retry_delay_seconds

    def create_subscription(self, *, topic: str, endpoint: str, secret: str) -> WebhookSubscriptionRecord:
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            raise ValueError("webhook endpoint must start with http:// or https://")

        with self._session_factory() as session:
            existing = (
                session.query(WebhookSubscriptionORM)
                .filter(WebhookSubscriptionORM.topic == topic)
                .filter(WebhookSubscriptionORM.endpoint == endpoint)
                .first()
            )
            if existing is not None:
                existing.secret = secret
                existing.updated_at = datetime.now(timezone.utc)
                session.add(existing)
                session.commit()
                return self._to_subscription_record(existing)

            now = datetime.now(timezone.utc)
            subscription = WebhookSubscriptionORM(
                id=uuid4().hex[:12],
                topic=topic,
                endpoint=endpoint,
                secret=secret,
                status="active",
                created_at=now,
                updated_at=now,
            )
            session.add(subscription)
            session.commit()
            return self._to_subscription_record(subscription)

    def publish_event(
        self,
        *,
        topic: str,
        payload: dict,
        now: datetime | None = None,
    ) -> list[WebhookDeliveryRecord]:
        deliveries: list[WebhookDeliveryRecord] = []
        current_time = now or datetime.now(timezone.utc)

        with self._session_factory() as session:
            subscriptions = (
                session.query(WebhookSubscriptionORM)
                .filter(WebhookSubscriptionORM.topic == topic)
                .filter(WebhookSubscriptionORM.status == "active")
                .all()
            )

            for subscription in subscriptions:
                body = {"topic": topic, "payload": payload}
                encoded_body = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
                signature = self._sign_payload(subscription.secret, encoded_body)
                response_status: int | None = None
                error_message: str | None = None
                try:
                    response = self._client.post(
                        subscription.endpoint,
                        content=encoded_body,
                        headers={
                            "content-type": "application/json",
                            "x-certman-signature": signature,
                            "x-certman-topic": topic,
                        },
                    )
                    response_status = response.status_code
                    is_success = 200 <= response.status_code < 300
                    if not is_success:
                        error_message = f"HTTP {response.status_code}"
                except httpx.HTTPError as exc:
                    is_success = False
                    error_message = str(exc)

                delivery = WebhookDeliveryORM(
                    id=uuid4().hex[:12],
                    subscription_id=subscription.id,
                    topic=topic,
                    payload=encoded_body.decode("utf-8"),
                    status="delivered" if is_success else "retry",
                    attempts=1,
                    http_status=response_status,
                    error=None if is_success else error_message,
                    next_retry_at=None if is_success else current_time + timedelta(seconds=self._retry_delay_seconds),
                    created_at=current_time,
                    updated_at=current_time,
                )
                session.add(delivery)
                deliveries.append(self._to_delivery_record(delivery))

            session.commit()

        return deliveries

    def list_subscriptions(
        self,
        *,
        topic: str | None = None,
        status: str | None = None,
    ) -> list[WebhookSubscriptionRecord]:
        with self._session_factory() as session:
            query = session.query(WebhookSubscriptionORM)
            if topic is not None:
                query = query.filter(WebhookSubscriptionORM.topic == topic)
            if status is not None:
                query = query.filter(WebhookSubscriptionORM.status == status)
            subscriptions = query.order_by(WebhookSubscriptionORM.created_at.desc()).all()
            return [self._to_subscription_record(s) for s in subscriptions]

    def get_subscription(self, subscription_id: str) -> WebhookSubscriptionRecord | None:
        with self._session_factory() as session:
            sub = session.get(WebhookSubscriptionORM, subscription_id)
            return self._to_subscription_record(sub) if sub is not None else None

    def update_subscription(
        self,
        subscription_id: str,
        *,
        endpoint: str | None = None,
        secret: str | None = None,
        status: str | None = None,
    ) -> WebhookSubscriptionRecord | None:
        if endpoint is not None and not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            raise ValueError("webhook endpoint must start with http:// or https://")
        with self._session_factory() as session:
            sub = session.get(WebhookSubscriptionORM, subscription_id)
            if sub is None:
                return None
            if endpoint is not None:
                sub.endpoint = endpoint
            if secret is not None:
                sub.secret = secret
            if status is not None:
                sub.status = status
            sub.updated_at = datetime.now(timezone.utc)
            session.add(sub)
            session.commit()
            return self._to_subscription_record(sub)

    def delete_subscription(self, subscription_id: str) -> bool:
        with self._session_factory() as session:
            sub = session.get(WebhookSubscriptionORM, subscription_id)
            if sub is None:
                return False
            session.delete(sub)
            session.commit()
            return True

    @staticmethod
    def _sign_payload(secret: str, payload: bytes) -> str:
        return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    @staticmethod
    def _to_subscription_record(subscription: WebhookSubscriptionORM) -> WebhookSubscriptionRecord:
        return WebhookSubscriptionRecord(
            subscription_id=subscription.id,
            topic=subscription.topic,
            endpoint=subscription.endpoint,
            secret=subscription.secret,
            status=subscription.status,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )

    @staticmethod
    def _to_delivery_record(delivery: WebhookDeliveryORM) -> WebhookDeliveryRecord:
        return WebhookDeliveryRecord(
            delivery_id=delivery.id,
            subscription_id=delivery.subscription_id,
            topic=delivery.topic,
            status=delivery.status,
            attempts=delivery.attempts,
            http_status=delivery.http_status,
            error=delivery.error,
            next_retry_at=delivery.next_retry_at,
            created_at=delivery.created_at,
            updated_at=delivery.updated_at,
        )