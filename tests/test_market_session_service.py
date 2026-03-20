"""Tests for src.api.services.market_session_service module."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.api.services.market_session_service import MarketSessionPhase, get_market_session_state


_IST = ZoneInfo("Asia/Kolkata")
_HELSINKI = ZoneInfo("Europe/Helsinki")


def _ist(hour: int, minute: int, *, weekday: int = 0) -> datetime:
    """Create an IST datetime on a specific weekday (0=Mon, 6=Sun)."""
    # Start from Mon 2026-03-16 and add days to get desired weekday
    from datetime import timedelta
    base = datetime(2026, 3, 16, hour, minute, tzinfo=_IST)  # Monday
    return base + timedelta(days=weekday)


def test_market_open_during_session() -> None:
    now = _ist(10, 0, weekday=0)  # Mon 10:00
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.OPEN
    assert state.is_tradeable is True
    assert "Market Open" in state.label


def test_market_open_at_exact_open() -> None:
    now = _ist(9, 15, weekday=1)  # Tue 09:15
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.OPEN


def test_market_open_at_exact_close() -> None:
    now = _ist(15, 30, weekday=2)  # Wed 15:30
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.OPEN


def test_pre_open_phase() -> None:
    now = _ist(9, 5, weekday=0)  # Mon 09:05
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.PRE_OPEN
    assert state.is_tradeable is False


def test_post_close_phase() -> None:
    now = _ist(16, 0, weekday=0)  # Mon 16:00
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.POST_CLOSE
    assert state.is_tradeable is False


def test_regression_2026_03_19_is_not_market_holiday() -> None:
    """2026-03-19 is a normal trading day, so after-hours should be post-close."""
    now = datetime(2026, 3, 19, 16, 0, tzinfo=_IST)
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.POST_CLOSE
    assert state.label == "Post-Close"


def test_regression_late_2026_03_19_local_time_not_holiday() -> None:
    """Late local time on 2026-03-19 (Europe/Helsinki) maps to IST 2026-03-20 03:00."""
    now = datetime(2026, 3, 19, 23, 30, tzinfo=_HELSINKI)
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.CLOSED
    assert state.label == "Closed"


def test_real_2026_holiday_is_classified_as_market_holiday() -> None:
    """Holi (2026-03-03) is an NSE weekday trading holiday."""
    now = datetime(2026, 3, 3, 10, 0, tzinfo=_IST)
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.CLOSED
    assert state.label == "Market Holiday"


def test_2026_03_20_is_regular_trading_day_during_market_hours() -> None:
    """Regression: 2026-03-20 should not be treated as a holiday."""
    now = datetime(2026, 3, 20, 10, 0, tzinfo=_IST)
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.OPEN
    assert state.label == "Market Open"


def test_closed_early_morning() -> None:
    now = _ist(7, 0, weekday=0)  # Mon 07:00
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.CLOSED
    assert state.is_tradeable is False


def test_weekend_saturday() -> None:
    now = _ist(10, 0, weekday=5)  # Saturday
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.WEEKEND
    assert "Saturday" in state.label
    assert "Holiday" not in state.label
    assert state.is_tradeable is False


def test_weekend_sunday() -> None:
    now = _ist(10, 0, weekday=6)  # Sunday
    state = get_market_session_state(now)
    assert state.phase == MarketSessionPhase.WEEKEND
    assert "Sunday" in state.label


def test_state_to_dict_keys() -> None:
    state = get_market_session_state(_ist(10, 0))
    d = state.to_dict()
    expected_keys = {
        "phase", "label", "exchange", "timezone",
        "market_open_time", "market_close_time",
        "current_time_ist", "is_tradeable", "next_transition",
    }
    assert set(d.keys()) == expected_keys


def test_default_now_returns_valid_state() -> None:
    """Calling without explicit now should not raise."""
    state = get_market_session_state()
    assert state.phase in {p for p in MarketSessionPhase}
    assert isinstance(state.to_dict(), dict)
