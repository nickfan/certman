from __future__ import annotations

from certman.events import Event, EventBus


def test_event_bus_delivers_event_to_all_handlers() -> None:
    bus = EventBus()
    received: list[tuple[str, str]] = []

    def first(event: Event) -> None:
        received.append(("first", event.topic))

    def second(event: Event) -> None:
        received.append(("second", event.topic))

    bus.subscribe("job.completed", first)
    bus.subscribe("job.completed", second)
    bus.publish("job.completed", {"job_id": "job-1"})

    assert received == [("first", "job.completed"), ("second", "job.completed")]


def test_event_bus_continues_when_one_handler_fails() -> None:
    bus = EventBus()
    received: list[str] = []

    def broken(event: Event) -> None:
        raise RuntimeError("boom")

    def healthy(event: Event) -> None:
        received.append(event.topic)

    bus.subscribe("job.failed", broken)
    bus.subscribe("job.failed", healthy)
    bus.publish("job.failed", {"job_id": "job-1"})

    assert received == ["job.failed"]