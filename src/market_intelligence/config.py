"""
Configuration models for the Phase 6 market intelligence layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.scanners.config import normalize_timeframe


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    if not weights:
        raise ValueError("weights cannot be empty")
    clean: dict[str, float] = {}
    for key, value in weights.items():
        w = float(value)
        if w < 0:
            raise ValueError("weights cannot be negative")
        clean[str(key)] = w
    total = sum(clean.values())
    if total <= 0:
        raise ValueError("weights total must be > 0")
    return {k: v / total for k, v in clean.items()}


def _normalize_lookback_weights(weights: dict[int, float]) -> dict[int, float]:
    if not weights:
        raise ValueError("lookback weights cannot be empty")
    clean: dict[int, float] = {}
    for key, value in weights.items():
        k = int(key)
        w = float(value)
        if k <= 0:
            raise ValueError("lookback window keys must be > 0")
        if w < 0:
            raise ValueError("lookback weights cannot be negative")
        clean[k] = w
    total = sum(clean.values())
    if total <= 0:
        raise ValueError("lookback weights total must be > 0")
    return {k: v / total for k, v in clean.items()}


@dataclass
class BreadthConfig:
    timeframe: str = "1D"
    moving_average_period: int = 50
    new_high_low_lookback: int = 120
    ad_line_lookback: int = 60
    strong_ad_ratio_threshold: float = 1.2
    weak_ad_ratio_threshold: float = 0.8
    strong_pct_above_ma_threshold: float = 60.0
    weak_pct_above_ma_threshold: float = 40.0

    def __post_init__(self) -> None:
        self.timeframe = normalize_timeframe(self.timeframe)
        if self.moving_average_period < 2:
            raise ValueError("moving_average_period must be >= 2")
        if self.new_high_low_lookback < 5:
            raise ValueError("new_high_low_lookback must be >= 5")
        if self.ad_line_lookback < 5:
            raise ValueError("ad_line_lookback must be >= 5")


@dataclass
class SectorRotationConfig:
    timeframe: str = "1D"
    benchmark_symbol: str = "NIFTY50.NS"
    lookback_windows: list[int] = field(default_factory=lambda: [20, 60, 120])
    lookback_weights: dict[int, float] = field(
        default_factory=lambda: {20: 0.5, 60: 0.3, 120: 0.2}
    )
    leading_quantile: float = 0.33
    lagging_quantile: float = 0.33

    def __post_init__(self) -> None:
        self.timeframe = normalize_timeframe(self.timeframe)
        self.lookback_windows = sorted({int(v) for v in self.lookback_windows})
        if not self.lookback_windows:
            raise ValueError("lookback_windows cannot be empty")
        if min(self.lookback_windows) <= 0:
            raise ValueError("lookback_windows values must be > 0")
        self.lookback_weights = _normalize_lookback_weights(self.lookback_weights)
        for key in self.lookback_weights:
            if key not in self.lookback_windows:
                raise ValueError(f"lookback weight key {key} missing from lookback_windows")
        if not 0 < self.leading_quantile < 1:
            raise ValueError("leading_quantile must be in (0, 1)")
        if not 0 < self.lagging_quantile < 1:
            raise ValueError("lagging_quantile must be in (0, 1)")


@dataclass
class VolumeIntelligenceConfig:
    timeframe: str = "1D"
    spike_lookback: int = 20
    spike_multiple_threshold: float = 1.8
    accumulation_window: int = 10
    distribution_window: int = 10
    vw_momentum_window: int = 10
    accumulation_strength_threshold: float = 1.1
    distribution_strength_threshold: float = 1.1

    def __post_init__(self) -> None:
        self.timeframe = normalize_timeframe(self.timeframe)
        if self.spike_lookback < 2:
            raise ValueError("spike_lookback must be >= 2")
        if self.spike_multiple_threshold <= 0:
            raise ValueError("spike_multiple_threshold must be > 0")
        if self.accumulation_window < 2 or self.distribution_window < 2:
            raise ValueError("accumulation_window/distribution_window must be >= 2")
        if self.vw_momentum_window < 2:
            raise ValueError("vw_momentum_window must be >= 2")


@dataclass
class VolatilityRegimeConfig:
    timeframe: str = "1D"
    atr_period: int = 14
    atr_baseline_period: int = 50
    realized_vol_window: int = 20
    high_vol_threshold: float = 0.03
    low_vol_threshold: float = 0.01
    expansion_atr_ratio: float = 1.2
    contraction_atr_ratio: float = 0.8

    def __post_init__(self) -> None:
        self.timeframe = normalize_timeframe(self.timeframe)
        if self.atr_period < 2:
            raise ValueError("atr_period must be >= 2")
        if self.atr_baseline_period <= self.atr_period:
            raise ValueError("atr_baseline_period must be > atr_period")
        if self.realized_vol_window < 2:
            raise ValueError("realized_vol_window must be >= 2")
        if self.high_vol_threshold <= self.low_vol_threshold:
            raise ValueError("high_vol_threshold must be > low_vol_threshold")
        if self.expansion_atr_ratio <= 0:
            raise ValueError("expansion_atr_ratio must be > 0")
        if self.contraction_atr_ratio <= 0:
            raise ValueError("contraction_atr_ratio must be > 0")


@dataclass
class InstitutionalFlowConfig:
    enabled: bool = False
    flow_file: Optional[str] = None
    allow_missing_data: bool = True


@dataclass
class MarketStateConfig:
    benchmark_symbol: str = "NIFTY50.NS"
    timeframe: str = "1D"
    component_weights: dict[str, float] = field(
        default_factory=lambda: {
            "trend": 0.30,
            "breadth": 0.30,
            "sector": 0.20,
            "volatility": 0.20,
        }
    )

    def __post_init__(self) -> None:
        self.timeframe = normalize_timeframe(self.timeframe)
        self.component_weights = _normalize_weights(self.component_weights)


@dataclass
class MarketIntelligenceExportConfig:
    output_dir: str = "output/market_intelligence"
    write_csv: bool = True
    write_json: bool = True
    market_breadth_csv: str = "market_breadth.csv"
    sector_rotation_csv: str = "sector_rotation.csv"
    volume_signals_csv: str = "volume_signals.csv"
    volatility_regime_json: str = "volatility_regime.json"
    market_state_summary_json: str = "market_state_summary.json"
    manifest_json: str = "market_intelligence_manifest.json"

    def __post_init__(self) -> None:
        if not self.write_csv and not self.write_json:
            raise ValueError("At least one export format must be enabled")


@dataclass
class MarketIntelligenceConfig:
    provider_name: str = "csv"
    data_dir: str = "data"
    breadth: BreadthConfig = field(default_factory=BreadthConfig)
    sector_rotation: SectorRotationConfig = field(default_factory=SectorRotationConfig)
    volume: VolumeIntelligenceConfig = field(default_factory=VolumeIntelligenceConfig)
    volatility: VolatilityRegimeConfig = field(default_factory=VolatilityRegimeConfig)
    institutional_flow: InstitutionalFlowConfig = field(default_factory=InstitutionalFlowConfig)
    market_state: MarketStateConfig = field(default_factory=MarketStateConfig)
    export: MarketIntelligenceExportConfig = field(default_factory=MarketIntelligenceExportConfig)
    continue_on_error: bool = True
