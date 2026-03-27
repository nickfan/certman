from __future__ import annotations

from threading import Condition


class SubscriptionEventBus:
    """In-process event bus used by subscribe long-poll endpoints.

    A monotonically increasing revision is used as a cheap wake-up signal.
    Subscribers wait until revision changes or timeout is reached.
    """

    def __init__(self) -> None:
        self._cv = Condition()
        self._revision = 0

    def mark_updated(self) -> int:
        with self._cv:
            self._revision += 1
            self._cv.notify_all()
            return self._revision

    def revision(self) -> int:
        with self._cv:
            return self._revision

    def wait_for_update(self, *, last_seen_revision: int, timeout_seconds: float) -> int:
        timeout = max(0.0, timeout_seconds)
        with self._cv:
            if self._revision != last_seen_revision:
                return self._revision
            self._cv.wait(timeout=timeout)
            return self._revision


subscription_event_bus = SubscriptionEventBus()


def notify_assignment_candidates_updated() -> int:
    return subscription_event_bus.mark_updated()
