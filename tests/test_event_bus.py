from __future__ import annotations

from src.realtime.event_bus import EventBus


def test_event_bus_publish_and_subscribe() -> None:
    bus = EventBus(enabled=True)
    received: list[dict] = []

    def on_cycle(payload: dict) -> None:
        received.append(payload)

    bus.subscribe("cycle_completed", on_cycle)
    count = bus.publish("cycle_completed", {"cycle_id": 1})

    assert count == 1
    assert received == [{"cycle_id": 1}]
    assert len(bus.history()) == 1


def test_event_bus_wildcard_subscription() -> None:
    bus = EventBus(enabled=True)
    received: list[dict] = []

    def on_any(payload: dict) -> None:
        received.append(payload)

    bus.subscribe("*", on_any)
    count = bus.publish("snapshot_updated", {"top_picks": 3})

    assert count == 1
    assert received[0]["event_type"] == "snapshot_updated"
    assert received[0]["payload"]["top_picks"] == 3


def test_event_bus_disabled_does_not_dispatch() -> None:
    bus = EventBus(enabled=False)
    received: list[dict] = []

    def on_cycle(payload: dict) -> None:
        received.append(payload)

    bus.subscribe("cycle_completed", on_cycle)
    count = bus.publish("cycle_completed", {"cycle_id": 2})

    assert count == 0
    assert received == []
    assert len(bus.history()) == 0
