from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from spongebob.engine.models import Event

EventCallback = Callable[[Event], Any]


class EventBus:
    """Synchronous publish/subscribe event bus with isolated subscriber error handling."""

    def __init__(self) -> None:
        self._subscribers: list[tuple[str, EventCallback]] = []

    def subscribe(self, event_type_or_wildcard: str, callback: EventCallback) -> None:
        """Register a callback for a specific event type or '*' for all events."""
        if not isinstance(event_type_or_wildcard, str) or not event_type_or_wildcard:
            raise ValueError("event_type_or_wildcard must be a non-empty string")
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._subscribers.append((event_type_or_wildcard, callback))

    def publish(self, event: Event) -> None:
        """Synchronously deliver an event to matching subscribers in registration order."""
        for sub_type, callback in list(self._subscribers):
            if sub_type == "*" or sub_type == event.type:
                try:
                    callback(event)
                except Exception:
                    continue


def replay(events: Iterable[Event], bus: EventBus) -> None:
    """Publish a sequence of recorded events onto an EventBus in order."""
    for event in events:
        bus.publish(event)
