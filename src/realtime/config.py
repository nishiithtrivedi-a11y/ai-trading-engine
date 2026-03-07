"""
Configuration for the Phase 8 real-time market engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.decision.config import DecisionConfig
from src.monitoring.config import MonitoringConfig
from src.realtime.models import RealTimeMode
from src.scanners.config import normalize_timeframe

DEFAULT_REALTIME_CONFIG_PATH = "config/realtime.yaml"


def _is_hhmm(value: str) -> bool:
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) != 2:
        return False
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return False
    return 0 <= hour <= 23 and 0 <= minute <= 59


@dataclass
class RealtimeConfig:
    enabled: bool = False
    mode: RealTimeMode = RealTimeMode.OFF
    provider_name: str = "csv"
    poll_interval_seconds: int = 60
    only_during_market_hours: bool = True
    market_timezone: str = "Asia/Kolkata"
    market_open_time: str = "09:15"
    market_close_time: str = "15:30"
    enable_polling: bool = True
    enable_alert_dispatch: bool = True
    enable_scheduler: bool = True
    enable_event_bus: bool = True
    enable_live_provider: bool = False
    persist_snapshots: bool = True
    persist_alerts: bool = True
    snapshot_persistence_enabled: bool = True
    max_cycles_per_run: int = 5
    dry_run: bool = False
    output_dir: str = "output/realtime"
    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=lambda: ["1D"])
    continue_on_error: bool = True

    def __post_init__(self) -> None:
        if self.poll_interval_seconds < 1:
            raise ValueError("poll_interval_seconds must be >= 1")
        if self.max_cycles_per_run < 1:
            raise ValueError("max_cycles_per_run must be >= 1")
        if not _is_hhmm(self.market_open_time):
            raise ValueError("market_open_time must be in HH:MM format")
        if not _is_hhmm(self.market_close_time):
            raise ValueError("market_close_time must be in HH:MM format")

        try:
            self.mode = self.mode if isinstance(self.mode, RealTimeMode) else RealTimeMode(str(self.mode))
        except ValueError as exc:
            raise ValueError(f"Unsupported realtime mode: {self.mode}") from exc

        self.symbols = list(dict.fromkeys(str(s).strip().upper() for s in self.symbols if str(s).strip()))
        self.timeframes = [normalize_timeframe(tf) for tf in self.timeframes]

        if not self.enabled:
            self.mode = RealTimeMode.OFF
        elif self.mode == RealTimeMode.OFF:
            raise ValueError("mode cannot be 'off' when realtime enabled=true")

        if self.mode == RealTimeMode.POLLING and not self.enable_polling:
            raise ValueError("mode='polling' requires enable_polling=true")


@dataclass
class RealTimeEngineConfig:
    realtime: RealtimeConfig = field(default_factory=RealtimeConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)


def load_realtime_config(
    config_path: Optional[str] = None,
    base_config: Optional[RealTimeEngineConfig] = None,
) -> RealTimeEngineConfig:
    """
    Load realtime settings from YAML file.

    The YAML is expected to contain a top-level `realtime:` mapping.
    Missing file and missing PyYAML both gracefully fall back to defaults.
    """
    cfg = base_config or RealTimeEngineConfig()
    path = Path(config_path or DEFAULT_REALTIME_CONFIG_PATH)
    if not path.exists():
        return cfg

    try:
        import yaml
    except ImportError:
        return cfg

    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    realtime_raw: dict[str, Any] = raw.get("realtime", {}) if isinstance(raw, dict) else {}
    if not isinstance(realtime_raw, dict):
        raise ValueError("Invalid realtime config format: 'realtime' must be a mapping")

    merged = dict(cfg.realtime.__dict__)
    merged.update(realtime_raw)
    cfg.realtime = RealtimeConfig(**merged)
    return cfg
