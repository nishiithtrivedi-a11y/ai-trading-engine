"""
Phase 8 realtime orchestration engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.realtime.alert_dispatcher import AlertDispatcher
from src.realtime.config import RealTimeEngineConfig
from src.realtime.data_poller import DataPoller
from src.realtime.event_bus import EventBus
from src.realtime.exporter import RealTimeExporter
from src.realtime.market_clock import MarketClock
from src.realtime.models import (
    RealTimeCycleResult,
    RealTimeCycleStatus,
    RealTimeEngineStatus,
    RealTimeMode,
    RealTimeRunResult,
    SnapshotRefreshResult,
)
from src.realtime.snapshot_refresher import SnapshotRefresher
from src.realtime.state_store import RealTimeStateStore


class RealTimeEngineError(Exception):
    """Raised when realtime engine fails and continue_on_error is disabled."""


@dataclass
class RealTimeEngine:
    config: RealTimeEngineConfig
    data_poller: Optional[DataPoller] = None
    market_clock: Optional[MarketClock] = None
    state_store: Optional[RealTimeStateStore] = None
    event_bus: Optional[EventBus] = None
    alert_dispatcher: Optional[AlertDispatcher] = None
    snapshot_refresher: Optional[SnapshotRefresher] = None
    exporter: Optional[RealTimeExporter] = None

    def __post_init__(self) -> None:
        self.data_poller = self.data_poller or DataPoller(provider_name=self.config.realtime.provider_name)
        self.market_clock = self.market_clock or MarketClock()
        self.state_store = self.state_store or RealTimeStateStore()
        self.event_bus = self.event_bus or EventBus(enabled=self.config.realtime.enable_event_bus)
        self.alert_dispatcher = self.alert_dispatcher or AlertDispatcher()
        self.snapshot_refresher = self.snapshot_refresher or SnapshotRefresher(
            monitoring_config=self.config.monitoring,
            decision_config=self.config.decision,
        )
        self.exporter = self.exporter or RealTimeExporter()

        self._running = False
        self._stop_requested = False
        self._cycle_counter = 0

    def start(self) -> None:
        if self._running:
            return
        self._stop_requested = False
        self._running = True
        self.state_store.mark_started()

    def stop(self) -> None:
        self._stop_requested = True
        if self._running:
            self._running = False
            self.state_store.mark_stopped()

    def status(self) -> dict:
        state = self.state_store.status()
        state.update(
            {
                "running": self._running,
                "stop_requested": self._stop_requested,
                "enabled": self.config.realtime.enabled,
                "mode": self.config.realtime.mode.value,
                "max_cycles_per_run": self.config.realtime.max_cycles_per_run,
            }
        )
        return state

    def run(self, export: bool = True) -> RealTimeRunResult:
        run_result = RealTimeRunResult(
            status=RealTimeEngineStatus.IDLE,
            enabled=self.config.realtime.enabled,
            mode=self.config.realtime.mode,
        )

        if not self.config.realtime.enabled or self.config.realtime.mode == RealTimeMode.OFF:
            run_result.status = RealTimeEngineStatus.DISABLED
            run_result.completed_at = pd.Timestamp.now(tz="UTC")
            run_result.warnings.append("Realtime engine disabled by config (enabled=false or mode=off)")
            self.state_store.mark_disabled()
            return run_result

        self.start()
        if self.event_bus.enabled:
            self.event_bus.publish("engine_started", {"mode": self.config.realtime.mode.value})

        try:
            for _ in range(self.config.realtime.max_cycles_per_run):
                if self._stop_requested:
                    break
                cycle = self.run_cycle()
                run_result.cycle_results.append(cycle)
        except Exception as exc:  # noqa: BLE001
            run_result.status = RealTimeEngineStatus.ERROR
            run_result.errors.append(str(exc))
            self.state_store.mark_error()
            if not self.config.realtime.continue_on_error:
                self.stop()
                run_result.completed_at = pd.Timestamp.now(tz="UTC")
                raise RealTimeEngineError(str(exc)) from exc
        finally:
            self.stop()

        if run_result.status != RealTimeEngineStatus.ERROR:
            run_result.status = RealTimeEngineStatus.STOPPED
        run_result.completed_at = pd.Timestamp.now(tz="UTC")

        if self.event_bus.enabled:
            self.event_bus.publish(
                "engine_stopped",
                {
                    "total_cycles": len(run_result.cycle_results),
                    "completed_cycles": run_result.completed_cycles,
                    "failed_cycles": run_result.failed_cycles,
                    "skipped_cycles": run_result.skipped_cycles,
                },
            )

        if export:
            outputs = self.exporter.export_all(run_result, self.config.realtime)
            run_result.exports = {k: str(v) for k, v in outputs.items()}

        return run_result

    def run_cycle(self) -> RealTimeCycleResult:
        self._cycle_counter += 1
        cycle = RealTimeCycleResult(cycle_id=self._cycle_counter)

        if self.event_bus.enabled:
            self.event_bus.publish("cycle_started", {"cycle_id": cycle.cycle_id})

        try:
            market_open = self.market_clock.is_market_open(self.config.realtime)
            cycle.market_open = market_open
            if not market_open:
                cycle.status = RealTimeCycleStatus.SKIPPED
                cycle.skipped_reason = "market_closed"
                cycle.warnings.append("Cycle skipped because market is closed")
                if self.event_bus.enabled:
                    self.event_bus.publish(
                        "market_closed",
                        {"cycle_id": cycle.cycle_id, "reason": cycle.skipped_reason},
                    )
                return cycle

            symbols = self._resolve_symbols()
            if not symbols:
                cycle.status = RealTimeCycleStatus.SKIPPED
                cycle.skipped_reason = "no_symbols"
                cycle.warnings.append("No symbols available for realtime cycle")
                return cycle
            timeframes = self._resolve_timeframes()

            poll = self.data_poller.poll(symbols=symbols, timeframes=timeframes, config=self.config.realtime)
            cycle.poll_result = poll
            cycle.warnings.extend(poll.warnings)
            cycle.errors.extend(poll.errors)

            refresh = self.snapshot_refresher.refresh()
            self._apply_refresh(cycle, refresh)

            dispatched = self.alert_dispatcher.dispatch(refresh.alerts, self.config.realtime)
            cycle.alerts = dispatched

            self.state_store.update_results(
                poll_result=poll,
                scan_result=refresh.monitoring_result.scan_result,
                monitoring_result=refresh.monitoring_result,
                pick_result=refresh.pick_result,
                snapshot=refresh.snapshot,
                alerts=dispatched,
            )

            cycle.status = RealTimeCycleStatus.COMPLETED

            if self.event_bus.enabled:
                self.event_bus.publish(
                    "snapshot_updated",
                    {"cycle_id": cycle.cycle_id, "top_picks": len(refresh.snapshot.top_picks)},
                )
                if dispatched:
                    self.event_bus.publish(
                        "alert_generated",
                        {"cycle_id": cycle.cycle_id, "alert_count": len(dispatched)},
                    )
        except Exception as exc:  # noqa: BLE001
            cycle.status = RealTimeCycleStatus.FAILED
            cycle.errors.append(str(exc))
            if self.event_bus.enabled:
                self.event_bus.publish(
                    "provider_error",
                    {"cycle_id": cycle.cycle_id, "error": str(exc)},
                )
            if not self.config.realtime.continue_on_error:
                raise
        finally:
            cycle.completed_at = pd.Timestamp.now(tz="UTC")
            self.state_store.record_cycle(cycle)
            if self.event_bus.enabled:
                self.event_bus.publish(
                    "cycle_completed",
                    {"cycle_id": cycle.cycle_id, "status": cycle.status.value},
                )

        return cycle

    @staticmethod
    def _apply_refresh(cycle: RealTimeCycleResult, refresh: SnapshotRefreshResult) -> None:
        cycle.snapshot = refresh.snapshot
        cycle.warnings.extend(refresh.warnings)
        cycle.errors.extend(refresh.errors)

    def _resolve_symbols(self) -> list[str]:
        if self.config.realtime.symbols:
            return list(self.config.realtime.symbols)

        symbols: list[str] = []
        for watchlist in self.config.monitoring.get_enabled_watchlists():
            symbols.extend([str(s).strip().upper() for s in watchlist.symbols if str(s).strip()])
        if symbols:
            return list(dict.fromkeys(symbols))

        return []

    def _resolve_timeframes(self) -> list[str]:
        if self.config.realtime.timeframes:
            return list(self.config.realtime.timeframes)
        return list(self.config.monitoring.scanner_config.timeframes)
