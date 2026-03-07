"""
Optional local scheduling primitives for repeated monitoring runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from src.monitoring.models import ScheduleMode, ScheduleSpec


class SchedulerError(Exception):
    """Raised when schedule calculations fail."""


@dataclass
class Scheduler:
    schedule: ScheduleSpec

    def next_run_time(self, from_time: Optional[pd.Timestamp] = None) -> Optional[pd.Timestamp]:
        if not self.schedule.enabled:
            return None
        if self.schedule.mode == ScheduleMode.MANUAL:
            return None

        base = self._to_schedule_timezone(from_time or pd.Timestamp.now(tz="UTC"))

        if self.schedule.mode == ScheduleMode.INTERVAL:
            if not self.schedule.interval_minutes:
                raise SchedulerError("interval_minutes must be set for interval schedule")
            return base + pd.Timedelta(minutes=self.schedule.interval_minutes)

        if self.schedule.mode == ScheduleMode.DAILY:
            if not self.schedule.daily_time:
                raise SchedulerError("daily_time must be set for daily schedule")
            target_time = self._parse_daily_time(self.schedule.daily_time)
            candidate = base.normalize() + pd.Timedelta(hours=target_time.hour, minutes=target_time.minute)
            if candidate <= base:
                candidate = candidate + pd.Timedelta(days=1)
            return candidate

        raise SchedulerError(f"Unsupported schedule mode: {self.schedule.mode}")

    def plan_runs(
        self,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
        max_runs: int = 100,
    ) -> list[pd.Timestamp]:
        if max_runs < 1:
            raise SchedulerError("max_runs must be >= 1")
        if end_time <= start_time:
            return []

        start = self._to_schedule_timezone(start_time)
        end = self._to_schedule_timezone(end_time)

        runs: list[pd.Timestamp] = []
        cursor = start
        while len(runs) < max_runs:
            nxt = self.next_run_time(cursor)
            if nxt is None or nxt > end:
                break
            runs.append(nxt)
            cursor = nxt
        return runs

    def _to_schedule_timezone(self, ts: pd.Timestamp) -> pd.Timestamp:
        try:
            tz = ZoneInfo(self.schedule.timezone)
        except Exception as exc:  # noqa: BLE001
            raise SchedulerError(f"Invalid schedule timezone '{self.schedule.timezone}'") from exc

        if ts.tzinfo is None:
            return ts.tz_localize(tz)
        return ts.tz_convert(tz)

    @staticmethod
    def _parse_daily_time(value: str) -> time:
        clean = str(value).strip()
        parts = clean.split(":")
        if len(parts) != 2:
            raise SchedulerError("daily_time must be in HH:MM format")
        hour = int(parts[0])
        minute = int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise SchedulerError("daily_time must be in HH:MM 24h range")
        return time(hour=hour, minute=minute)
