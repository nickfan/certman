from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class Event:
    topic: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[Event], None]]] = {}

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        event = Event(topic=topic, payload=payload)
        for handler in self._handlers.get(topic, []):
            try:
                handler(event)
            except Exception:
                continue