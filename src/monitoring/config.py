"""
Configuration models for the Phase 4 market monitoring layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.monitoring.models import ScheduleMode, ScheduleSpec
from src.scanners.config import ScannerConfig, normalize_timeframe


def _normalize_positive_weights(weights: dict[int, float]) -> dict[int, float]:
    if not weights:
        raise ValueError("weights cannot be empty")
    cleaned: dict[int, float] = {}
    for key, value in weights.items():
        lookback = int(key)
        weight = float(value)
        if lookback <= 0:
            raise ValueError("lookback window keys must be > 0")
        if weight < 0:
            raise ValueError("weights cannot be negative")
        cleaned[lookback] = weight

    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("weights sum must be > 0")
    return {k: v / total for k, v in cleaned.items()}


@dataclass
class WatchlistDefinition:
    name: str
    symbols: list[str] = field(default_factory=list)
    universe_name: Optional[str] = None
    file_path: Optional[str] = None
    file_format: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    default_timeframes: list[str] = field(default_factory=list)
    enabled: bool = True

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("watchlist name cannot be empty")

        has_symbols = bool(self.symbols)
        has_universe = bool(self.universe_name)
        has_file = bool(self.file_path)

        if not any([has_symbols, has_universe, has_file]):
            raise ValueError(
                "watchlist definition requires one source: symbols, universe_name, or file_path"
            )

        self.symbols = [str(s).strip().upper() for s in self.symbols if str(s).strip()]
        self.tags = [str(tag).strip().lower() for tag in self.tags if str(tag).strip()]
        self.default_timeframes = [normalize_timeframe(tf) for tf in self.default_timeframes]

        if self.file_format is not None:
            fmt = str(self.file_format).strip().lower()
            if fmt not in {"csv", "json"}:
                raise ValueError("file_format must be one of: csv, json")
            self.file_format = fmt


@dataclass
class RegimeDetectorConfig:
    benchmark_symbol: str = "NIFTY50.NS"
    timeframe: str = "1D"
    trend_fast_period: int = 20
    trend_slow_period: int = 50
    volatility_period: int = 14
    high_volatility_threshold: float = 0.035
    low_volatility_threshold: float = 0.008
    rangebound_width_threshold: float = 0.025
    bullish_slope_threshold: float = 0.0
    bearish_slope_threshold: float = 0.0
    use_benchmark: bool = True
    fallback_to_symbol: bool = True

    def __post_init__(self) -> None:
        self.timeframe = normalize_timeframe(self.timeframe)
        if self.trend_fast_period < 2:
            raise ValueError("trend_fast_period must be >= 2")
        if self.trend_slow_period <= self.trend_fast_period:
            raise ValueError("trend_slow_period must be > trend_fast_period")
        if self.volatility_period < 2:
            raise ValueError("volatility_period must be >= 2")
        if self.high_volatility_threshold <= 0:
            raise ValueError("high_volatility_threshold must be > 0")
        if self.low_volatility_threshold <= 0:
            raise ValueError("low_volatility_threshold must be > 0")
        if self.high_volatility_threshold <= self.low_volatility_threshold:
            raise ValueError("high_volatility_threshold must be > low_volatility_threshold")
        if self.rangebound_width_threshold <= 0:
            raise ValueError("rangebound_width_threshold must be > 0")


@dataclass
class RelativeStrengthConfig:
    benchmark_symbol: str = "NIFTY50.NS"
    timeframe: str = "1D"
    lookback_windows: list[int] = field(default_factory=lambda: [20, 60, 120])
    lookback_weights: dict[int, float] = field(
        default_factory=lambda: {20: 0.4, 60: 0.35, 120: 0.25}
    )
    top_n: int = 20
    min_history_bars: int = 150
    sector_map_file: Optional[str] = None
    allow_missing_benchmark: bool = True

    def __post_init__(self) -> None:
        self.timeframe = normalize_timeframe(self.timeframe)
        self.lookback_windows = sorted({int(v) for v in self.lookback_windows})
        if not self.lookback_windows:
            raise ValueError("lookback_windows cannot be empty")
        if min(self.lookback_windows) <= 0:
            raise ValueError("lookback_windows values must be > 0")

        self.lookback_weights = _normalize_positive_weights(self.lookback_weights)
        for window in self.lookback_weights:
            if window not in self.lookback_windows:
                raise ValueError(
                    f"lookback_weights key {window} missing from lookback_windows {self.lookback_windows}"
                )

        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")
        if self.min_history_bars < 5:
            raise ValueError("min_history_bars must be >= 5")


@dataclass
class AlertEngineConfig:
    enabled: bool = True
    min_opportunity_score: float = 65.0
    high_priority_score: float = 85.0
    dedupe_window_minutes: int = 180
    include_regime_change_alerts: bool = True
    include_relative_strength_alerts: bool = True
    relative_strength_top_n: int = 10
    include_watchlist_actionable_alerts: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.min_opportunity_score <= 100:
            raise ValueError("min_opportunity_score must be in [0, 100]")
        if not 0 <= self.high_priority_score <= 100:
            raise ValueError("high_priority_score must be in [0, 100]")
        if self.high_priority_score < self.min_opportunity_score:
            raise ValueError("high_priority_score must be >= min_opportunity_score")
        if self.dedupe_window_minutes < 0:
            raise ValueError("dedupe_window_minutes must be >= 0")
        if self.relative_strength_top_n < 1:
            raise ValueError("relative_strength_top_n must be >= 1")


@dataclass
class SnapshotConfig:
    top_n: int = 10
    min_score: float = 0.0
    include_regime_context: bool = True
    include_relative_strength_context: bool = True
    include_watchlist_context: bool = True

    def __post_init__(self) -> None:
        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")
        if not 0 <= self.min_score <= 100:
            raise ValueError("min_score must be in [0, 100]")


@dataclass
class MonitoringExportConfig:
    output_dir: str = "output/monitoring"
    write_csv: bool = True
    write_json: bool = True
    alerts_csv_filename: str = "alerts.csv"
    alerts_json_filename: str = "alerts.json"
    top_picks_csv_filename: str = "top_picks.csv"
    market_snapshot_json_filename: str = "market_snapshot.json"
    relative_strength_csv_filename: str = "relative_strength.csv"
    relative_strength_json_filename: str = "relative_strength.json"
    regime_summary_json_filename: str = "regime_summary.json"
    manifest_json_filename: str = "monitoring_run_manifest.json"

    def __post_init__(self) -> None:
        if not self.write_csv and not self.write_json:
            raise ValueError("At least one export format must be enabled")


@dataclass
class MonitoringConfig:
    scanner_config: ScannerConfig = field(default_factory=ScannerConfig)
    watchlists: list[WatchlistDefinition] = field(default_factory=list)
    regime: RegimeDetectorConfig = field(default_factory=RegimeDetectorConfig)
    relative_strength: RelativeStrengthConfig = field(default_factory=RelativeStrengthConfig)
    alerts: AlertEngineConfig = field(default_factory=AlertEngineConfig)
    snapshot: SnapshotConfig = field(default_factory=SnapshotConfig)
    schedule: ScheduleSpec = field(
        default_factory=lambda: ScheduleSpec(name="manual_default", mode=ScheduleMode.MANUAL)
    )
    export: MonitoringExportConfig = field(default_factory=MonitoringExportConfig)
    continue_on_error: bool = True

    def get_enabled_watchlists(self) -> list[WatchlistDefinition]:
        return [w for w in self.watchlists if w.enabled]
