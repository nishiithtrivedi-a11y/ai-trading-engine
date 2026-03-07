"""
Market clock helpers for realtime cycle gating.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.realtime.config import RealtimeConfig


class MarketClockError(Exception):
    """Raised when market clock evaluation fails."""


def _parse_hhmm(value: str) -> time:
    try:
        hh, mm = str(value).split(":")
        return time(hour=int(hh), minute=int(mm))
    except Exception as exc:  # noqa: BLE001
        raise MarketClockError(f"Invalid HH:MM time: {value}") from exc


@dataclass
class MarketClock:
    def is_market_open(
        self,
        config: RealtimeConfig,
        now: datetime | None = None,
    ) -> bool:
        if config.dry_run:
            return True
        if not config.only_during_market_hours:
            return True

        local_now = self._to_local(now, config.market_timezone)
        if local_now.weekday() >= 5:
            return False

        open_time = _parse_hhmm(config.market_open_time)
        close_time = _parse_hhmm(config.market_close_time)
        local_t = local_now.time().replace(second=0, microsecond=0)
        return open_time <= local_t <= close_time

    def next_run_time(
        self,
        config: RealtimeConfig,
        now: datetime | None = None,
    ) -> datetime:
        local_now = self._to_local(now, config.market_timezone)
        interval = timedelta(seconds=int(config.poll_interval_seconds))

        if config.dry_run or not config.only_during_market_hours:
            return local_now + interval

        if self.is_market_open(config=config, now=local_now):
            candidate = local_now + interval
            close_time = _parse_hhmm(config.market_close_time)
            if (
                candidate.weekday() < 5
                and candidate.time().replace(second=0, microsecond=0) <= close_time
            ):
                return candidate
            return self._next_session_open(local_now + timedelta(days=1), config)

        return self._next_session_open(local_now, config)

    def seconds_until_next_run(
        self,
        config: RealtimeConfig,
        now: datetime | None = None,
    ) -> int:
        local_now = self._to_local(now, config.market_timezone)
        nxt = self.next_run_time(config=config, now=local_now)
        return max(0, int((nxt - local_now).total_seconds()))

    @staticmethod
    def _to_local(now: datetime | None, timezone: str) -> datetime:
        tz = ZoneInfo(timezone)
        if now is None:
            return datetime.now(tz=tz)
        if now.tzinfo is None:
            return now.replace(tzinfo=tz)
        return now.astimezone(tz)

    @staticmethod
    def _next_session_open(from_dt: datetime, config: RealtimeConfig) -> datetime:
        open_time = _parse_hhmm(config.market_open_time)
        close_time = _parse_hhmm(config.market_close_time)
        candidate = from_dt

        # Move to next weekday.
        while candidate.weekday() >= 5:
            candidate = candidate + timedelta(days=1)

        today_open = candidate.replace(
            hour=open_time.hour,
            minute=open_time.minute,
            second=0,
            microsecond=0,
        )
        today_close = candidate.replace(
            hour=close_time.hour,
            minute=close_time.minute,
            second=0,
            microsecond=0,
        )

        if candidate <= today_open:
            return today_open
        if candidate > today_close:
            candidate = candidate + timedelta(days=1)
            while candidate.weekday() >= 5:
                candidate = candidate + timedelta(days=1)
            return candidate.replace(
                hour=open_time.hour,
                minute=open_time.minute,
                second=0,
                microsecond=0,
            )
        return candidate
