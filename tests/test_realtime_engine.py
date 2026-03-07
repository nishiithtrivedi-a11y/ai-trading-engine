from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.decision.config import DecisionConfig
from src.decision.models import PickRunResult
from src.monitoring.config import MonitoringConfig
from src.monitoring.models import MonitoringRunResult
from src.realtime.config import RealTimeEngineConfig, RealtimeConfig
from src.realtime.event_bus import EventBus
from src.realtime.models import (
    PollResult,
    PolledSymbolData,
    RealTimeEngineStatus,
    RealTimeMode,
    RealTimeSnapshot,
    RealtimeAlertRecord,
    SnapshotRefreshResult,
)
from src.realtime.realtime_engine import RealTimeEngine


@dataclass
class _FakeClock:
    is_open: bool = True

    def is_market_open(self, config, now=None) -> bool:
        return self.is_open


@dataclass
class _FakePoller:
    calls: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def poll(self, symbols, timeframes, config) -> PollResult:
        self.calls += 1
        return PollResult(
            mode=config.mode,
            records=[
                PolledSymbolData(
                    symbol=symbols[0],
                    timeframe=timeframes[0],
                    timestamp=pd.Timestamp("2026-03-07T10:00:00Z"),
                    close_price=123.0,
                    bars=100,
                    source="fake",
                    success=len(self.errors) == 0,
                    message="; ".join(self.errors) if self.errors else "",
                )
            ],
            warnings=list(self.warnings),
            errors=list(self.errors),
        )


@dataclass
class _FakeRefresher:
    calls: int = 0
    raises: bool = False

    def refresh(self, watchlist_names=None) -> SnapshotRefreshResult:
        self.calls += 1
        if self.raises:
            raise RuntimeError("refresh failed")
        return SnapshotRefreshResult(
            monitoring_result=MonitoringRunResult(),
            pick_result=PickRunResult(),
            snapshot=RealTimeSnapshot(top_picks=[{"symbol": "RELIANCE.NS"}]),
            alerts=[
                RealtimeAlertRecord(
                    alert_id=f"a{self.calls}",
                    severity="warning",
                    title="Actionable",
                    message="RELIANCE buy",
                    timestamp=pd.Timestamp("2026-03-07T10:00:00Z"),
                    symbol="RELIANCE.NS",
                    dedupe_key="dup",
                )
            ],
        )


def _engine_config(**kwargs) -> RealTimeEngineConfig:
    defaults = {
        "enabled": True,
        "mode": RealTimeMode.SIMULATED,
        "only_during_market_hours": False,
        "max_cycles_per_run": 3,
        "symbols": ["RELIANCE.NS"],
        "timeframes": ["1D"],
    }
    defaults.update(kwargs)
    rt = RealtimeConfig(**defaults)
    return RealTimeEngineConfig(
        realtime=rt,
        monitoring=MonitoringConfig(),
        decision=DecisionConfig(),
    )


def test_realtime_engine_disabled_path_returns_clean_status() -> None:
    cfg = RealTimeEngineConfig(realtime=RealtimeConfig(enabled=False), monitoring=MonitoringConfig(), decision=DecisionConfig())
    engine = RealTimeEngine(config=cfg)
    out = engine.run(export=False)
    assert out.status == RealTimeEngineStatus.DISABLED
    assert out.total_cycles == 0
    assert engine.status()["engine_status"] == RealTimeEngineStatus.DISABLED.value


def test_realtime_engine_enabled_simulated_runs_finite_cycles() -> None:
    poller = _FakePoller()
    refresher = _FakeRefresher()
    engine = RealTimeEngine(
        config=_engine_config(max_cycles_per_run=3),
        data_poller=poller,
        market_clock=_FakeClock(is_open=True),
        snapshot_refresher=refresher,
    )
    out = engine.run(export=False)
    assert out.status == RealTimeEngineStatus.STOPPED
    assert out.total_cycles == 3
    assert out.completed_cycles == 3
    assert poller.calls == 3
    assert refresher.calls == 3


def test_realtime_engine_market_closed_skips_cycles() -> None:
    poller = _FakePoller()
    refresher = _FakeRefresher()
    engine = RealTimeEngine(
        config=_engine_config(max_cycles_per_run=2, only_during_market_hours=True),
        data_poller=poller,
        market_clock=_FakeClock(is_open=False),
        snapshot_refresher=refresher,
    )
    out = engine.run(export=False)
    assert out.total_cycles == 2
    assert out.skipped_cycles == 2
    assert poller.calls == 0
    assert refresher.calls == 0


def test_realtime_engine_publishes_cycle_events() -> None:
    poller = _FakePoller()
    refresher = _FakeRefresher()
    bus = EventBus(enabled=True)
    events: list[dict] = []
    bus.subscribe("cycle_completed", lambda payload: events.append(payload))

    engine = RealTimeEngine(
        config=_engine_config(max_cycles_per_run=1),
        data_poller=poller,
        market_clock=_FakeClock(is_open=True),
        snapshot_refresher=refresher,
        event_bus=bus,
    )
    out = engine.run(export=False)
    assert out.total_cycles == 1
    assert len(events) == 1
    assert events[0]["status"] == "completed"


def test_realtime_engine_polling_mode_graceful_with_poller_errors() -> None:
    poller = _FakePoller(
        warnings=["provider does not support live fetch; fallback"],
        errors=["live fetch unavailable"],
    )
    refresher = _FakeRefresher()
    cfg = _engine_config(
        mode=RealTimeMode.POLLING,
        enable_live_provider=True,
        max_cycles_per_run=1,
    )
    engine = RealTimeEngine(
        config=cfg,
        data_poller=poller,
        market_clock=_FakeClock(is_open=True),
        snapshot_refresher=refresher,
    )

    out = engine.run(export=False)
    assert out.status == RealTimeEngineStatus.STOPPED
    assert out.total_cycles == 1
    assert out.cycle_results[0].status.value == "completed"
    assert "live fetch unavailable" in out.cycle_results[0].errors
