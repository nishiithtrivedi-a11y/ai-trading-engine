"""
Market session state service.

Wraps existing market_sessions and market_clock logic to expose
a clean, API-ready market session state.  Used by the platform
status aggregation layer and by the frontend for UX gating.

SAFETY: This module is read-only — no execution paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import Any, Optional
from zoneinfo import ZoneInfo


class MarketSessionPhase(str, Enum):
    """Current market session phase."""
    PRE_OPEN = "pre_open"
    OPEN = "open"
    POST_CLOSE = "post_close"
    CLOSED = "closed"
    WEEKEND = "weekend"
    UNKNOWN = "unknown"


# IST (Asia/Kolkata) NSE session boundaries
_MARKET_TZ = "Asia/Kolkata"
_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)
_PRE_OPEN_START = time(9, 0)


@dataclass(frozen=True)
class MarketSessionState:
    """Snapshot of the current market session."""
    phase: MarketSessionPhase
    label: str
    exchange: str = "NSE"
    timezone: str = _MARKET_TZ
    market_open_time: str = "09:15"
    market_close_time: str = "15:30"
    current_time_ist: str = ""
    is_tradeable: bool = False
    next_transition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "label": self.label,
            "exchange": self.exchange,
            "timezone": self.timezone,
            "market_open_time": self.market_open_time,
            "market_close_time": self.market_close_time,
            "current_time_ist": self.current_time_ist,
            "is_tradeable": self.is_tradeable,
            "next_transition": self.next_transition,
        }


def get_market_session_state(
    now: Optional[datetime] = None,
) -> MarketSessionState:
    """Compute the current market session phase.

    Uses simple time-window logic against IST.  Does NOT consult
    an exchange holiday calendar — if a public holiday falls on a
    weekday, the system will report ``OPEN`` during market hours.
    The UI should surface an appropriate note about this limitation.
    """
    tz = ZoneInfo(_MARKET_TZ)

    if now is None:
        local_now = datetime.now(tz=tz)
    elif now.tzinfo is None:
        local_now = now.replace(tzinfo=tz)
    else:
        local_now = now.astimezone(tz)

    current_time_ist = local_now.strftime("%H:%M:%S")
    current_t = local_now.time().replace(second=0, microsecond=0)
    weekday = local_now.weekday()  # 0=Mon, 6=Sun

    # Weekend
    if weekday >= 5:
        day_name = "Saturday" if weekday == 5 else "Sunday"
        return MarketSessionState(
            phase=MarketSessionPhase.WEEKEND,
            label=f"Weekend ({day_name})",
            current_time_ist=current_time_ist,
            is_tradeable=False,
            next_transition="Monday 09:15 IST",
        )

    # Pre-open (09:00–09:14)
    if _PRE_OPEN_START <= current_t < _MARKET_OPEN:
        return MarketSessionState(
            phase=MarketSessionPhase.PRE_OPEN,
            label="Pre-Open",
            current_time_ist=current_time_ist,
            is_tradeable=False,
            next_transition="Market opens at 09:15 IST",
        )

    # Market open (09:15–15:30)
    if _MARKET_OPEN <= current_t <= _MARKET_CLOSE:
        return MarketSessionState(
            phase=MarketSessionPhase.OPEN,
            label="Market Open",
            current_time_ist=current_time_ist,
            is_tradeable=True,
            next_transition=f"Closes at 15:30 IST",
        )

    # Post-close (15:31–23:59)
    if current_t > _MARKET_CLOSE:
        return MarketSessionState(
            phase=MarketSessionPhase.POST_CLOSE,
            label="Post-Close",
            current_time_ist=current_time_ist,
            is_tradeable=False,
            next_transition="Next session 09:15 IST",
        )

    # Before pre-open (00:00–08:59)
    return MarketSessionState(
        phase=MarketSessionPhase.CLOSED,
        label="Closed",
        current_time_ist=current_time_ist,
        is_tradeable=False,
        next_transition="Pre-open at 09:00 IST",
    )
