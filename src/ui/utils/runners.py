"""
Engine runner wrappers for the Control Center UI.

Each function wraps an engine invocation in a safe try/except shell,
returning a structured ``RunResult`` so the UI layer never crashes.

These runners create sensible default configs for the CSV provider and
delegate entirely to the existing engine classes — no business logic
is duplicated here.
"""

from __future__ import annotations

import glob
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    """Structured outcome of a single engine run."""

    success: bool
    engine_name: str
    message: str
    output_dir: Optional[str] = None
    duration_seconds: float = 0.0
    error_details: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "engine_name": self.engine_name,
            "message": self.message,
            "output_dir": self.output_dir,
            "duration_seconds": round(self.duration_seconds, 2),
            "error_details": self.error_details,
            "artifacts": self.artifacts,
        }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _default_strategy_specs() -> list:
    """Return default RSI + SMA strategy scan specs."""
    from src.scanners.config import StrategyScanSpec
    from src.strategies.registry import resolve_strategy

    specs = []
    for strat_key in ["rsi_reversion", "sma_crossover"]:
        try:
            s = resolve_strategy(strat_key)
            specs.append(
                StrategyScanSpec(
                    strategy_class=s.strategy_class,
                    params=dict(s.params),
                    timeframes=["1D"],
                )
            )
        except Exception:
            pass

    return specs


def _default_scanner_config(output_dir: str = "output") -> "ScannerConfig":
    """Create a ScannerConfig with sensible CSV-provider defaults."""
    from src.scanners.config import ExportConfig, ScannerConfig

    scanner_output = str(Path(output_dir) / "scanner")
    return ScannerConfig(
        universe_name="nifty50",
        provider_name="csv",
        data_dir="data",
        timeframes=["1D"],
        strategy_specs=_default_strategy_specs(),
        export=ExportConfig(output_dir=scanner_output),
    )


def _default_monitoring_config(output_dir: str = "output") -> "MonitoringConfig":
    """Create a MonitoringConfig with default scanner + watchlist."""
    from src.monitoring.config import (
        MonitoringConfig,
        MonitoringExportConfig,
        WatchlistDefinition,
    )

    scanner_cfg = _default_scanner_config(output_dir)
    monitoring_output = str(Path(output_dir) / "monitoring")
    return MonitoringConfig(
        scanner_config=scanner_cfg,
        watchlists=[
            WatchlistDefinition(
                name="nifty50",
                universe_name="nifty50",
            ),
        ],
        export=MonitoringExportConfig(output_dir=monitoring_output),
    )


def _default_symbols() -> tuple:
    """Return (symbols_list, sector_symbol_map) from NSE universe."""
    try:
        from src.data.nse_universe import NSEUniverseLoader

        loader = NSEUniverseLoader()
        symbols = loader.get_nifty50()[:10]  # use first 10 for speed
    except Exception:
        symbols = [
            "RELIANCE.NS", "TCS.NS", "INFY.NS",
            "HDFCBANK.NS", "ICICIBANK.NS",
        ]

    sector_map = {
        "IT": [s for s in symbols if any(
            k in s.upper() for k in ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"]
        )],
        "BANKING": [s for s in symbols if any(
            k in s.upper() for k in ["HDFC", "ICICI", "KOTAK", "AXIS", "SBI"]
        )],
        "ENERGY": [s for s in symbols if any(
            k in s.upper() for k in ["RELIANCE", "ONGC", "NTPC", "POWER"]
        )],
    }
    # Remove empty sectors
    sector_map = {k: v for k, v in sector_map.items() if v}

    return symbols, sector_map


def _find_data_file(data_dir: str = "data") -> Optional[str]:
    """Find the first available 1D CSV data file."""
    pattern = str(Path(data_dir) / "*_1D.csv")
    matches = sorted(glob.glob(pattern))
    if matches:
        return matches[0]
    # Fall back to any CSV
    pattern = str(Path(data_dir) / "*.csv")
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Engine runners
# ---------------------------------------------------------------------------

def run_scanner(output_dir: str = "output") -> RunResult:
    """Run the Phase 3 stock scanner engine."""
    t0 = time.time()
    try:
        from src.scanners.engine import StockScannerEngine

        config = _default_scanner_config(output_dir)
        engine = StockScannerEngine(scanner_config=config)
        result = engine.run(export=True)

        n_opps = len(result.opportunities) if result.opportunities else 0
        artifacts = {}
        if hasattr(result, "exports") and result.exports:
            artifacts = {k: str(v) for k, v in result.exports.items()}

        return RunResult(
            success=True,
            engine_name="Scanner",
            message=f"Scan complete: {n_opps} opportunities found "
                    f"({result.num_symbols_scanned} symbols scanned)",
            output_dir=config.export.output_dir,
            duration_seconds=time.time() - t0,
            artifacts=artifacts,
        )
    except Exception as exc:
        return RunResult(
            success=False,
            engine_name="Scanner",
            message=f"Scanner failed: {exc}",
            duration_seconds=time.time() - t0,
            error_details=str(exc),
        )


def run_monitoring(output_dir: str = "output") -> RunResult:
    """Run the Phase 4 market monitoring engine."""
    t0 = time.time()
    try:
        from src.monitoring.market_monitor import MarketMonitor

        config = _default_monitoring_config(output_dir)
        monitor = MarketMonitor(config=config)
        result = monitor.run(export=True)

        n_alerts = len(result.alerts) if result.alerts else 0
        artifacts = {}
        if hasattr(result, "exports") and result.exports:
            artifacts = {k: str(v) for k, v in result.exports.items()}

        return RunResult(
            success=True,
            engine_name="Monitoring",
            message=f"Monitoring complete: {n_alerts} alerts generated",
            output_dir=config.export.output_dir,
            duration_seconds=time.time() - t0,
            artifacts=artifacts,
        )
    except Exception as exc:
        return RunResult(
            success=False,
            engine_name="Monitoring",
            message=f"Monitoring failed: {exc}",
            duration_seconds=time.time() - t0,
            error_details=str(exc),
        )


def run_decision_engine(output_dir: str = "output") -> RunResult:
    """Run the Phase 5 decision/pick engine.

    This runs monitoring first (which includes scanning), then pipes
    the result to the pick engine.
    """
    t0 = time.time()
    try:
        from src.decision.config import DecisionConfig, DecisionExportConfig
        from src.decision.exporter import DecisionExporter
        from src.decision.pick_engine import PickEngine
        from src.monitoring.market_monitor import MarketMonitor

        # Run monitoring to get scan + monitoring results
        mon_config = _default_monitoring_config(output_dir)
        monitor = MarketMonitor(config=mon_config)
        mon_result = monitor.run(export=True)

        # Run decision engine with monitoring result
        decision_output = str(Path(output_dir) / "decision")
        decision_cfg = DecisionConfig(
            export=DecisionExportConfig(output_dir=decision_output),
        )
        pick_engine = PickEngine(decision_config=decision_cfg)
        pick_result = pick_engine.run(monitoring_result=mon_result)

        # Export decision results
        exporter = DecisionExporter()
        exports = exporter.export_all(pick_result, decision_cfg.export)

        n_picks = len(pick_result.selected_picks) if pick_result.selected_picks else 0
        n_rejected = len(pick_result.rejected_opportunities) if pick_result.rejected_opportunities else 0
        artifacts = {k: str(v) for k, v in exports.items()}

        return RunResult(
            success=True,
            engine_name="Decision Engine",
            message=f"Decision complete: {n_picks} picks selected, "
                    f"{n_rejected} rejected",
            output_dir=decision_output,
            duration_seconds=time.time() - t0,
            artifacts=artifacts,
        )
    except Exception as exc:
        return RunResult(
            success=False,
            engine_name="Decision Engine",
            message=f"Decision engine failed: {exc}",
            duration_seconds=time.time() - t0,
            error_details=str(exc),
        )


def run_market_intelligence(output_dir: str = "output") -> RunResult:
    """Run the Phase 6 market intelligence engine."""
    t0 = time.time()
    try:
        from src.market_intelligence.config import (
            MarketIntelligenceConfig,
            MarketIntelligenceExportConfig,
        )
        from src.market_intelligence.exporter import MarketIntelligenceExporter
        from src.market_intelligence.market_state_engine import MarketStateEngine

        symbols, sector_map = _default_symbols()

        mi_output = str(Path(output_dir) / "market_intelligence")
        config = MarketIntelligenceConfig(
            provider_name="csv",
            data_dir="data",
            export=MarketIntelligenceExportConfig(output_dir=mi_output),
        )

        engine = MarketStateEngine()
        result = engine.run(
            symbols=symbols,
            sector_symbol_map=sector_map,
            config=config,
            benchmark_symbol="NIFTY50.NS",
        )

        # Export
        exporter = MarketIntelligenceExporter()
        exports = exporter.export_all(result, config.export)
        artifacts = {k: str(v) for k, v in exports.items()}

        state_label = "N/A"
        if hasattr(result, "market_state") and result.market_state:
            ms = result.market_state
            state_label = getattr(ms, "trend_state", "N/A")

        return RunResult(
            success=True,
            engine_name="Market Intelligence",
            message=f"Market intelligence complete: trend={state_label}, "
                    f"{len(symbols)} symbols analyzed",
            output_dir=mi_output,
            duration_seconds=time.time() - t0,
            artifacts=artifacts,
        )
    except Exception as exc:
        return RunResult(
            success=False,
            engine_name="Market Intelligence",
            message=f"Market intelligence failed: {exc}",
            duration_seconds=time.time() - t0,
            error_details=str(exc),
        )


def run_research_lab(
    output_dir: str = "output",
    data_file: Optional[str] = None,
) -> RunResult:
    """Run the Phase 7 strategy research lab."""
    t0 = time.time()
    try:
        from src.core.data_handler import DataHandler
        from src.research_lab.config import (
            ResearchLabExportConfig,
            StrategyDiscoveryConfig,
        )
        from src.research_lab.strategy_discovery_engine import StrategyDiscoveryEngine
        from src.utils.config import BacktestConfig

        # Find a data file
        file_path = data_file or _find_data_file()
        if not file_path or not Path(file_path).exists():
            return RunResult(
                success=False,
                engine_name="Research Lab",
                message="No data file found. Place CSV files in the data/ directory.",
                duration_seconds=time.time() - t0,
                error_details="No CSV data files available in data/ directory",
            )

        handler = DataHandler.from_csv(file_path)

        lab_output = str(Path(output_dir) / "research_lab")
        base_cfg = BacktestConfig(
            data_source="csv",
            data_file=file_path,
        )
        discovery_cfg = StrategyDiscoveryConfig(
            top_n=10,
            export=ResearchLabExportConfig(output_dir=lab_output),
        )

        engine = StrategyDiscoveryEngine()
        result = engine.run(
            base_config=base_cfg,
            data_handler=handler,
            config=discovery_cfg,
            export=True,
        )

        n_scores = len(result.strategy_scores) if result.strategy_scores else 0
        artifacts = {}
        if hasattr(result, "exports") and result.exports:
            artifacts = {k: str(v) for k, v in result.exports.items()}

        return RunResult(
            success=True,
            engine_name="Research Lab",
            message=f"Research lab complete: {n_scores} strategies scored "
                    f"(data: {Path(file_path).name})",
            output_dir=lab_output,
            duration_seconds=time.time() - t0,
            artifacts=artifacts,
        )
    except Exception as exc:
        return RunResult(
            success=False,
            engine_name="Research Lab",
            message=f"Research lab failed: {exc}",
            duration_seconds=time.time() - t0,
            error_details=str(exc),
        )


def run_realtime_once(output_dir: str = "output") -> RunResult:
    """Run a single realtime cycle (safe, bounded, simulated)."""
    t0 = time.time()
    try:
        from src.realtime.config import RealTimeEngineConfig, RealtimeConfig
        from src.realtime.models import RealTimeMode
        from src.realtime.realtime_engine import RealTimeEngine

        rt_output = str(Path(output_dir) / "realtime")

        mon_config = _default_monitoring_config(output_dir)
        from src.decision.config import DecisionConfig

        rt_cfg = RealTimeEngineConfig(
            realtime=RealtimeConfig(
                enabled=True,
                mode=RealTimeMode.SIMULATED,
                provider_name="csv",
                max_cycles_per_run=1,
                only_during_market_hours=False,
                persist_snapshots=True,
                persist_alerts=True,
                output_dir=rt_output,
                timeframes=["1D"],
            ),
            monitoring=mon_config,
            decision=DecisionConfig(),
        )

        engine = RealTimeEngine(config=rt_cfg)
        result = engine.run(export=True)

        completed = result.completed_cycles if hasattr(result, "completed_cycles") else 0
        artifacts = {}
        if hasattr(result, "exports") and result.exports:
            artifacts = {k: str(v) for k, v in result.exports.items()}

        return RunResult(
            success=True,
            engine_name="Realtime (Single Cycle)",
            message=f"Realtime cycle complete: {completed} cycle(s) ran "
                    f"(mode=simulated)",
            output_dir=rt_output,
            duration_seconds=time.time() - t0,
            artifacts=artifacts,
        )
    except Exception as exc:
        return RunResult(
            success=False,
            engine_name="Realtime (Single Cycle)",
            message=f"Realtime cycle failed: {exc}",
            duration_seconds=time.time() - t0,
            error_details=str(exc),
        )


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_full_pipeline(
    output_dir: str = "output",
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> List[RunResult]:
    """Run the main research pipeline: MI -> Scanner -> Monitoring -> Decision.

    Stops on the first hard failure and reports which step failed.

    Parameters
    ----------
    output_dir : str
        Root output directory.
    progress_callback : callable, optional
        Called as ``callback(stage_name, step_index, total_steps)``
        before each step starts.

    Returns
    -------
    list[RunResult]
        One result per step attempted.
    """
    stages: list[tuple[str, Callable]] = [
        ("Market Intelligence", lambda: run_market_intelligence(output_dir)),
        ("Scanner", lambda: run_scanner(output_dir)),
        ("Monitoring", lambda: run_monitoring(output_dir)),
        ("Decision Engine", lambda: run_decision_engine(output_dir)),
    ]

    results: list[RunResult] = []
    total = len(stages)

    for idx, (name, runner) in enumerate(stages):
        if progress_callback:
            progress_callback(name, idx, total)

        result = runner()
        results.append(result)

        if not result.success:
            # Stop pipeline on failure
            break

    return results


# ---------------------------------------------------------------------------
# Config status helpers
# ---------------------------------------------------------------------------

def get_realtime_config_status() -> Dict[str, Any]:
    """Read the realtime config file and return a status dict."""
    try:
        from src.realtime.config import load_realtime_config

        cfg = load_realtime_config()
        rt = cfg.realtime
        return {
            "enabled": rt.enabled,
            "mode": str(rt.mode.value) if hasattr(rt.mode, "value") else str(rt.mode),
            "provider": rt.provider_name,
            "max_cycles": rt.max_cycles_per_run,
            "market_hours_only": rt.only_during_market_hours,
            "poll_interval": rt.poll_interval_seconds,
            "symbols": rt.symbols,
            "timeframes": rt.timeframes,
            "output_dir": rt.output_dir,
        }
    except Exception as exc:
        return {
            "enabled": False,
            "mode": "off",
            "error": str(exc),
        }


def get_provider_status() -> Dict[str, Any]:
    """Return current provider configuration status."""
    try:
        from src.data.provider_config import DataProvidersConfig

        config = DataProvidersConfig()
        default = config.default_provider
        providers = {}
        for name, entry in config.providers.items():
            providers[name] = {
                "enabled": entry.enabled,
                "data_dir": entry.data_dir,
            }
        return {
            "default_provider": default,
            "providers": providers,
        }
    except Exception:
        return {
            "default_provider": "csv",
            "providers": {"csv": {"enabled": True, "data_dir": "data/"}},
        }
