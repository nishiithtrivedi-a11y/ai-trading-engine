from __future__ import annotations

import pandas as pd

from src.monitoring.models import ScheduleMode, ScheduleSpec
from src.monitoring.scheduler import Scheduler


def test_interval_next_run_time() -> None:
    spec = ScheduleSpec(
        name="interval_15m",
        mode=ScheduleMode.INTERVAL,
        enabled=True,
        interval_minutes=15,
        timezone="Asia/Kolkata",
    )
    scheduler = Scheduler(spec)
    base = pd.Timestamp("2026-03-07 09:00:00", tz="Asia/Kolkata")

    nxt = scheduler.next_run_time(base)
    assert nxt == pd.Timestamp("2026-03-07 09:15:00", tz="Asia/Kolkata")


def test_daily_next_run_time_same_day_or_next_day() -> None:
    spec = ScheduleSpec(
        name="daily",
        mode=ScheduleMode.DAILY,
        enabled=True,
        daily_time="09:30",
        timezone="Asia/Kolkata",
    )
    scheduler = Scheduler(spec)

    before = pd.Timestamp("2026-03-07 09:00:00", tz="Asia/Kolkata")
    after = pd.Timestamp("2026-03-07 10:00:00", tz="Asia/Kolkata")

    nxt_before = scheduler.next_run_time(before)
    nxt_after = scheduler.next_run_time(after)

    assert nxt_before == pd.Timestamp("2026-03-07 09:30:00", tz="Asia/Kolkata")
    assert nxt_after == pd.Timestamp("2026-03-08 09:30:00", tz="Asia/Kolkata")


def test_disabled_or_manual_schedule_returns_none() -> None:
    spec = ScheduleSpec(name="manual", mode=ScheduleMode.MANUAL, enabled=True)
    scheduler = Scheduler(spec)
    assert scheduler.next_run_time() is None

    disabled = ScheduleSpec(
        name="interval_disabled",
        mode=ScheduleMode.INTERVAL,
        enabled=False,
        interval_minutes=10,
    )
    assert Scheduler(disabled).next_run_time() is None


def test_plan_runs_interval() -> None:
    spec = ScheduleSpec(
        name="interval_30m",
        mode=ScheduleMode.INTERVAL,
        enabled=True,
        interval_minutes=30,
        timezone="UTC",
    )
    scheduler = Scheduler(spec)
    start = pd.Timestamp("2026-03-07 00:00:00", tz="UTC")
    end = pd.Timestamp("2026-03-07 02:00:00", tz="UTC")

    runs = scheduler.plan_runs(start, end, max_runs=10)
    assert len(runs) == 4
    assert runs[0] == pd.Timestamp("2026-03-07 00:30:00", tz="UTC")
    assert runs[-1] == pd.Timestamp("2026-03-07 02:00:00", tz="UTC")
