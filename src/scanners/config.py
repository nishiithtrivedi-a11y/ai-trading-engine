"""
Scanner configuration models.

These configs are intentionally lightweight and explicit so scanner
modules can be composed and tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.strategies.base_strategy import BaseStrategy


_SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "1D"}


def normalize_timeframe(value: str) -> str:
    clean = str(value).strip()
    if not clean:
        raise ValueError("timeframe cannot be empty")

    key = clean.lower()
    alias_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "60m": "1h",
        "1d": "1D",
        "d": "1D",
        "day": "1D",
        "daily": "1D",
    }
    normalized = alias_map.get(key, clean)

    if normalized not in _SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe '{value}'. Supported: {sorted(_SUPPORTED_TIMEFRAMES)}"
        )
    return normalized


class SetupMode(str, Enum):
    FIXED_PCT = "fixed_pct"
    ATR_R_MULTIPLE = "atr_r_multiple"


@dataclass
class ExportConfig:
    output_dir: str = "output/scanner"
    csv_filename: str = "opportunities.csv"
    json_filename: str = "opportunities.json"
    write_csv: bool = True
    write_json: bool = True

    def __post_init__(self) -> None:
        if not self.write_csv and not self.write_json:
            raise ValueError("At least one export format must be enabled")


@dataclass
class StrategyScanSpec:
    strategy_class: type[BaseStrategy]
    params: dict[str, Any] = field(default_factory=dict)
    timeframes: list[str] = field(default_factory=list)
    enabled: bool = True

    def __post_init__(self) -> None:
        self.timeframes = [normalize_timeframe(tf) for tf in self.timeframes]

    @property
    def strategy_name(self) -> str:
        return self.strategy_class.__name__


@dataclass
class ScannerConfig:
    universe_name: str = "nifty50"
    custom_universe_file: Optional[str] = None
    provider_name: str = "csv"
    data_dir: str = "data"
    timeframes: list[str] = field(default_factory=lambda: ["5m", "15m", "1h", "1D"])
    strategy_specs: list[StrategyScanSpec] = field(default_factory=list)

    min_history_bars: int = 120
    top_n: int = 25

    setup_mode: SetupMode = SetupMode.ATR_R_MULTIPLE
    setup_fixed_stop_pct: float = 0.02
    setup_atr_period: int = 14
    setup_stop_atr_mult: float = 1.5
    setup_target_rr: float = 2.0

    # Setup sanity filters
    setup_min_stop_distance_pct: float = 0.003
    setup_max_stop_distance_pct: float = 0.20
    setup_min_rr: float = 1.2

    score_weights: dict[str, float] = field(
        default_factory=lambda: {
            "signal": 0.35,
            "risk_reward": 0.35,
            "trend": 0.20,
            "liquidity": 0.10,
            "freshness": 0.0,
        }
    )

    skip_on_data_error: bool = True
    graceful_provider_errors: bool = True

    export: ExportConfig = field(default_factory=ExportConfig)
    # Optional analysis framework wiring (Phase 4). Disabled by default to
    # preserve existing scanner behavior unless explicitly enabled.
    enable_analysis_features: bool = False
    analysis_profile: str = ""
    analysis_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.timeframes = [normalize_timeframe(tf) for tf in self.timeframes]

        if self.min_history_bars < 2:
            raise ValueError("min_history_bars must be >= 2")
        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")

        if self.setup_fixed_stop_pct <= 0:
            raise ValueError("setup_fixed_stop_pct must be > 0")
        if self.setup_atr_period < 2:
            raise ValueError("setup_atr_period must be >= 2")
        if self.setup_stop_atr_mult <= 0:
            raise ValueError("setup_stop_atr_mult must be > 0")
        if self.setup_target_rr <= 0:
            raise ValueError("setup_target_rr must be > 0")

        if self.setup_min_stop_distance_pct <= 0:
            raise ValueError("setup_min_stop_distance_pct must be > 0")
        if self.setup_max_stop_distance_pct <= 0:
            raise ValueError("setup_max_stop_distance_pct must be > 0")
        if self.setup_max_stop_distance_pct <= self.setup_min_stop_distance_pct:
            raise ValueError("setup_max_stop_distance_pct must be > setup_min_stop_distance_pct")
        if self.setup_min_rr <= 0:
            raise ValueError("setup_min_rr must be > 0")

        self.score_weights = self._normalize_weights(self.score_weights)

    def get_effective_timeframes(self, spec: StrategyScanSpec) -> list[str]:
        if spec.timeframes:
            return spec.timeframes
        return self.timeframes

    @staticmethod
    def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
        if not weights:
            raise ValueError("score_weights cannot be empty")

        clean: dict[str, float] = {}
        for key, value in weights.items():
            weight = float(value)
            if weight < 0:
                raise ValueError("score_weights cannot contain negative values")
            clean[str(key)] = weight

        total = sum(clean.values())
        if total <= 0:
            raise ValueError("score_weights total must be > 0")

        return {k: v / total for k, v in clean.items()}
