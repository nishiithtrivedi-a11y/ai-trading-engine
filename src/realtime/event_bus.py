"""
Lightweight in-memory event bus for realtime components.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, DefaultDict

import pandas as pd


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


@dataclass
class EventRecord:
    event_type: str
    payload: dict[str, Any]
    timestamp: pd.Timestamp = field(default_factory=_now_utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class EventBus:
    enabled: bool = True
    max_history: int = 500
    _subscribers: DefaultDict[str, list[Callable[[dict[str, Any]], None]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _history: list[EventRecord] = field(default_factory=list)

    def subscribe(self, event_type: str, callback: Callable[[dict[str, Any]], None]) -> None:
        if not callable(callback):
            raise ValueError("callback must be callable")
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[dict[str, Any]], None]) -> None:
        if event_type not in self._subscribers:
            return
        self._subscribers[event_type] = [cb for cb in self._subscribers[event_type] if cb is not callback]

    def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        if not self.enabled:
            return 0

        event = EventRecord(event_type=event_type, payload=dict(payload))
        self._history.append(event)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history :]

        count = 0
        for cb in list(self._subscribers.get(event_type, [])):
            cb(dict(payload))
            count += 1
        for cb in list(self._subscribers.get("*", [])):
            cb({"event_type": event_type, "payload": dict(payload)})
            count += 1
        return count

    def clear(self) -> None:
        self._history.clear()
        self._subscribers.clear()

    def history(self) -> list[EventRecord]:
        return list(self._history)
