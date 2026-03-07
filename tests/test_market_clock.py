from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.realtime.config import RealtimeConfig
from src.realtime.market_clock import MarketClock
from src.realtime.models import RealTimeMode


def _ist_dt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_market_open_during_session() -> None:
    cfg = RealtimeConfig(enabled=True, mode=RealTimeMode.SIMULATED)
    clock = MarketClock()
    now = _ist_dt(2026, 3, 2, 10, 0)  # Monday
    assert clock.is_market_open(cfg, now=now) is True


def test_market_closed_outside_session_and_weekend() -> None:
    cfg = RealtimeConfig(enabled=True, mode=RealTimeMode.SIMULATED)
    clock = MarketClock()
    before_open = _ist_dt(2026, 3, 2, 8, 45)  # Monday
    weekend = _ist_dt(2026, 3, 1, 11, 0)  # Sunday
    assert clock.is_market_open(cfg, now=before_open) is False
    assert clock.is_market_open(cfg, now=weekend) is False


def test_market_gate_can_be_disabled() -> None:
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        only_during_market_hours=False,
    )
    clock = MarketClock()
    weekend = _ist_dt(2026, 3, 1, 11, 0)  # Sunday
    assert clock.is_market_open(cfg, now=weekend) is True


def test_dry_run_always_open() -> None:
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        dry_run=True,
    )
    clock = MarketClock()
    weekend = _ist_dt(2026, 3, 1, 11, 0)  # Sunday
    assert clock.is_market_open(cfg, now=weekend) is True


def test_next_run_time_inside_market_session_uses_interval() -> None:
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        poll_interval_seconds=120,
    )
    clock = MarketClock()
    now = _ist_dt(2026, 3, 2, 10, 0)  # Monday
    nxt = clock.next_run_time(cfg, now=now)
    assert nxt == _ist_dt(2026, 3, 2, 10, 2)


def test_next_run_time_after_close_moves_to_next_session_open() -> None:
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        poll_interval_seconds=60,
    )
    clock = MarketClock()
    now = _ist_dt(2026, 3, 6, 16, 0)  # Friday after close
    nxt = clock.next_run_time(cfg, now=now)
    assert nxt == _ist_dt(2026, 3, 9, 9, 15)  # Monday open


def test_seconds_until_next_run_non_negative() -> None:
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        poll_interval_seconds=30,
    )
    clock = MarketClock()
    now = _ist_dt(2026, 3, 2, 10, 0)
    assert clock.seconds_until_next_run(cfg, now=now) == 30
