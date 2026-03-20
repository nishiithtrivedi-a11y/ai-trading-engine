"""
Central strategy library registry helpers.

This module keeps strategy discovery explicit and engine-safe:
- only signal-generation strategies are registered as runnable
- unsupported/deferred rows remain in the strategy manifest
- aliases resolve to canonical keys for backward compatibility
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.strategies.base_strategy import BaseStrategy
from src.strategies.breakout import BreakoutStrategy
from src.strategies.intraday.day_high_low_breakout import DayHighLowBreakoutStrategy
from src.strategies.intraday.gap_strategies import GapFadeStrategy, GapMomentumStrategy
from src.strategies.intraday.opening_range_breakout import OpeningRangeBreakoutStrategy
from src.strategies.intraday.pivot_point_reversal import PivotPointReversalStrategy
from src.strategies.intraday.relative_volume_breakout import RelativeVolumeBreakoutStrategy
from src.strategies.intraday.vwap_mean_reversion import VWAPMeanReversionStrategy
from src.strategies.intraday.vwap_pullback_trend import VWAPPullbackTrendStrategy
from src.strategies.intraday_trend_following_strategy import IntradayTrendFollowingStrategy
from src.strategies.positional.long_term_trend import LongTermTrendStrategy
from src.strategies.positional.time_series_momentum import TimeSeriesMomentumStrategy
from src.strategies.quant.pairs_zscore import PairsZScoreStrategy
from src.strategies.quant.relative_strength_rotation import RelativeStrengthRotationStrategy
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.strategies.swing.bollinger_reversion import BollingerReversionStrategy
from src.strategies.swing.moving_average_pullback import MovingAveragePullbackStrategy
from src.strategies.swing.price_channel_breakout import PriceChannelBreakoutStrategy

StrategyClass = type[BaseStrategy]


@dataclass(frozen=True)
class StrategySpec:
    key: str
    strategy_class: StrategyClass
    category: str
    mode: str = "full"
    params: dict[str, Any] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    spreadsheet_ids: tuple[str, ...] = ()
    description: str = ""

    def as_catalog_entry(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "class": self.strategy_class,
            "class_name": self.strategy_class.__name__,
            "module": self.strategy_class.__module__,
            "category": self.category,
            "mode": self.mode,
            "params": dict(self.params),
            "aliases": list(self.aliases),
            "spreadsheet_ids": list(self.spreadsheet_ids),
            "description": self.description,
        }

    def as_runtime_entry(self) -> dict[str, Any]:
        return {
            "class": self.strategy_class,
            "params": dict(self.params),
            "category": self.category,
            "mode": self.mode,
            "spreadsheet_ids": list(self.spreadsheet_ids),
            "description": self.description,
        }


_SPECS: tuple[StrategySpec, ...] = (
    StrategySpec(
        key="sma_crossover",
        strategy_class=SMACrossoverStrategy,
        category="positional",
        mode="full",
        aliases=("dual_moving_average_crossover",),
        spreadsheet_ids=("S064",),
        description="Dual moving average crossover trend model.",
    ),
    StrategySpec(
        key="rsi_reversion",
        strategy_class=RSIReversionStrategy,
        category="swing",
        mode="full",
        aliases=("rsi_oversold_bounce",),
        spreadsheet_ids=("S045",),
        description="RSI oversold/overbought mean-reversion setup.",
    ),
    StrategySpec(
        key="breakout",
        strategy_class=BreakoutStrategy,
        category="swing",
        mode="full",
        spreadsheet_ids=(),
        description="Base breakout strategy from legacy engine.",
    ),
    StrategySpec(
        key="intraday_trend_following",
        strategy_class=IntradayTrendFollowingStrategy,
        category="intraday",
        mode="full",
        spreadsheet_ids=(),
        description="Supertrend/EMA intraday trend-following strategy.",
    ),
    StrategySpec(
        key="opening_range_breakout",
        strategy_class=OpeningRangeBreakoutStrategy,
        category="intraday",
        mode="full",
        spreadsheet_ids=("S007",),
        description="Breakout above opening range high.",
    ),
    StrategySpec(
        key="opening_range_breakdown",
        strategy_class=OpeningRangeBreakoutStrategy,
        category="intraday",
        mode="full",
        params={"direction": "short"},
        spreadsheet_ids=("S008",),
        description="Breakdown below opening range low.",
    ),
    StrategySpec(
        key="vwap_pullback_long",
        strategy_class=VWAPPullbackTrendStrategy,
        category="intraday",
        mode="limited",
        params={"direction": "long"},
        spreadsheet_ids=("S009",),
        description="Limited VWAP pullback continuation proxy.",
    ),
    StrategySpec(
        key="vwap_breakdown_retest_short",
        strategy_class=VWAPPullbackTrendStrategy,
        category="intraday",
        mode="limited",
        params={"direction": "short"},
        spreadsheet_ids=("S010",),
        description="Limited VWAP breakdown retest continuation proxy.",
    ),
    StrategySpec(
        key="vwap_mean_reversion",
        strategy_class=VWAPMeanReversionStrategy,
        category="intraday",
        mode="full",
        spreadsheet_ids=("S011",),
        description="Mean-reversion around intraday VWAP.",
    ),
    StrategySpec(
        key="gap_and_go",
        strategy_class=GapMomentumStrategy,
        category="intraday",
        mode="full",
        spreadsheet_ids=("S012",),
        description="Gap continuation momentum setup.",
    ),
    StrategySpec(
        key="gap_fade",
        strategy_class=GapFadeStrategy,
        category="intraday",
        mode="full",
        spreadsheet_ids=("S013", "S032", "S047"),
        description="Gap fade mean-reversion setup.",
    ),
    StrategySpec(
        key="day_high_breakout",
        strategy_class=DayHighLowBreakoutStrategy,
        category="intraday",
        mode="limited",
        params={"direction": "long"},
        spreadsheet_ids=("S014",),
        description="Limited day-high momentum breakout proxy.",
    ),
    StrategySpec(
        key="day_low_breakdown",
        strategy_class=DayHighLowBreakoutStrategy,
        category="intraday",
        mode="limited",
        params={"direction": "short"},
        spreadsheet_ids=("S015",),
        description="Limited day-low momentum breakdown proxy.",
    ),
    StrategySpec(
        key="relative_volume_breakout",
        strategy_class=RelativeVolumeBreakoutStrategy,
        category="intraday",
        mode="full",
        spreadsheet_ids=("S024",),
        description="Breakout gated by relative volume expansion.",
    ),
    StrategySpec(
        key="pivot_point_reversal",
        strategy_class=PivotPointReversalStrategy,
        category="intraday",
        mode="full",
        spreadsheet_ids=("S033",),
        description="Reversal around prior-session pivot levels.",
    ),
    StrategySpec(
        key="moving_average_pullback",
        strategy_class=MovingAveragePullbackStrategy,
        category="swing",
        mode="full",
        spreadsheet_ids=("S020",),
        description="Pullback-to-MA continuation setup.",
    ),
    StrategySpec(
        key="pullback_to_20dma",
        strategy_class=MovingAveragePullbackStrategy,
        category="swing",
        mode="full",
        params={"trend_period": 50, "pullback_period": 20},
        spreadsheet_ids=("S037",),
        description="Pullback to 20DMA within prevailing trend.",
    ),
    StrategySpec(
        key="pullback_to_50dma",
        strategy_class=MovingAveragePullbackStrategy,
        category="swing",
        mode="full",
        params={"trend_period": 100, "pullback_period": 50},
        spreadsheet_ids=("S038",),
        description="Pullback to 50DMA within prevailing trend.",
    ),
    StrategySpec(
        key="bollinger_reversion",
        strategy_class=BollingerReversionStrategy,
        category="swing",
        mode="full",
        spreadsheet_ids=("S046", "S119", "S120", "S127", "S141"),
        description="Bollinger-band reversion setup.",
    ),
    StrategySpec(
        key="price_channel_breakout",
        strategy_class=PriceChannelBreakoutStrategy,
        category="swing",
        mode="full",
        spreadsheet_ids=("S043",),
        description="Price-channel breakout from prior range.",
    ),
    StrategySpec(
        key="donchian_swing_breakout",
        strategy_class=PriceChannelBreakoutStrategy,
        category="swing",
        mode="full",
        params={"lookback": 20},
        spreadsheet_ids=("S044",),
        description="Donchian-style swing breakout.",
    ),
    StrategySpec(
        key="weekly_momentum_continuation",
        strategy_class=TimeSeriesMomentumStrategy,
        category="swing",
        mode="full",
        params={"lookback": 20, "min_return_pct": 0.03, "trend_filter_period": 20},
        spreadsheet_ids=("S057",),
        description="Weekly momentum continuation proxy.",
    ),
    StrategySpec(
        key="high_52_week_breakout",
        strategy_class=PriceChannelBreakoutStrategy,
        category="positional",
        mode="full",
        params={"lookback": 252, "direction": "long"},
        spreadsheet_ids=("S058",),
        description="52-week high breakout proxy using 252-bar channel.",
    ),
    StrategySpec(
        key="time_series_momentum",
        strategy_class=TimeSeriesMomentumStrategy,
        category="positional",
        mode="full",
        spreadsheet_ids=(),
        description="General time-series momentum strategy.",
    ),
    StrategySpec(
        key="long_term_trend_following",
        strategy_class=LongTermTrendStrategy,
        category="positional",
        mode="full",
        spreadsheet_ids=("S062",),
        description="Long-term trend following model.",
    ),
    StrategySpec(
        key="trend_200dma_model",
        strategy_class=LongTermTrendStrategy,
        category="positional",
        mode="full",
        params={"trend_period": 200, "fast_period": 50},
        spreadsheet_ids=("S063",),
        description="200DMA trend regime model.",
    ),
    StrategySpec(
        key="turtle_donchian_breakout",
        strategy_class=PriceChannelBreakoutStrategy,
        category="positional",
        mode="full",
        params={"lookback": 55},
        spreadsheet_ids=("S065", "S099"),
        description="Turtle-style Donchian breakout.",
    ),
    StrategySpec(
        key="momentum_investing",
        strategy_class=TimeSeriesMomentumStrategy,
        category="positional",
        mode="full",
        params={"lookback": 252, "min_return_pct": 0.08, "trend_filter_period": 200},
        spreadsheet_ids=("S066",),
        description="Long-horizon momentum investing proxy.",
    ),
    StrategySpec(
        key="pairs_zscore_limited",
        strategy_class=PairsZScoreStrategy,
        category="quant",
        mode="limited",
        aliases=("pairs_zscore",),
        spreadsheet_ids=("S061", "S129", "S149"),
        description="Limited z-score pair spread model (requires aligned pair series).",
    ),
    StrategySpec(
        key="relative_strength_rotation_limited",
        strategy_class=RelativeStrengthRotationStrategy,
        category="quant",
        mode="limited",
        aliases=("relative_strength_rotation",),
        spreadsheet_ids=("S050", "S060", "S067"),
        description="Limited relative-strength leadership proxy.",
    ),
    StrategySpec(
        key="etf_lead_lag_rotation_limited",
        strategy_class=RelativeStrengthRotationStrategy,
        category="etf_index",
        mode="limited",
        params={"benchmark_col": "benchmark_close", "rs_lookback": 40, "rs_ma_period": 15},
        spreadsheet_ids=("S036",),
        description="Limited ETF lead-lag rotation proxy.",
    ),
    StrategySpec(
        key="sector_rotation_swing_limited",
        strategy_class=RelativeStrengthRotationStrategy,
        category="etf_index",
        mode="limited",
        params={"benchmark_col": "benchmark_close", "rs_lookback": 80, "rs_ma_period": 20},
        spreadsheet_ids=("S051", "S078"),
        description="Limited sector rotation proxy.",
    ),
    StrategySpec(
        key="cross_sectional_momentum_rotation_limited",
        strategy_class=RelativeStrengthRotationStrategy,
        category="quant",
        mode="limited",
        params={"benchmark_col": "benchmark_close", "rs_lookback": 120, "rs_ma_period": 30},
        spreadsheet_ids=("S067",),
        description="Limited cross-sectional momentum proxy.",
    ),
    StrategySpec(
        key="pairs_trade_swing_limited",
        strategy_class=PairsZScoreStrategy,
        category="relative_value",
        mode="limited",
        params={"lookback": 80, "entry_z": 2.0, "exit_z": 0.7},
        spreadsheet_ids=("S061",),
        description="Limited swing pair spread model.",
    ),
    StrategySpec(
        key="pairs_intraday_limited",
        strategy_class=PairsZScoreStrategy,
        category="relative_value",
        mode="limited",
        params={"lookback": 40, "entry_z": 2.2, "exit_z": 0.6},
        spreadsheet_ids=("S030",),
        description="Limited intraday pair spread model.",
    ),
    StrategySpec(
        key="statistical_reversion_basket_limited",
        strategy_class=PairsZScoreStrategy,
        category="quant",
        mode="limited",
        params={"lookback": 60, "entry_z": 1.8, "exit_z": 0.5},
        spreadsheet_ids=("S031", "S150"),
        description="Limited basket-reversion proxy using pair spread contract.",
    ),
    StrategySpec(
        key="futures_opening_range_breakout",
        strategy_class=OpeningRangeBreakoutStrategy,
        category="futures",
        mode="full",
        spreadsheet_ids=("S092",),
        description="Opening range breakout for futures bars.",
    ),
    StrategySpec(
        key="futures_trend_pullback",
        strategy_class=MovingAveragePullbackStrategy,
        category="futures",
        mode="full",
        params={"trend_period": 30, "pullback_period": 10},
        spreadsheet_ids=("S093",),
        description="Trend-day pullback proxy for futures.",
    ),
    StrategySpec(
        key="futures_vwap_reversion_limited",
        strategy_class=VWAPMeanReversionStrategy,
        category="futures",
        mode="limited",
        spreadsheet_ids=("S094",),
        description="Limited VWAP reversion proxy (no official settlement feed).",
    ),
    StrategySpec(
        key="futures_breakout_system",
        strategy_class=PriceChannelBreakoutStrategy,
        category="futures",
        mode="full",
        params={"lookback": 55},
        spreadsheet_ids=("S099",),
        description="Futures breakout system via channel breakout.",
    ),
    StrategySpec(
        key="futures_pullback_trend",
        strategy_class=MovingAveragePullbackStrategy,
        category="futures",
        mode="full",
        params={"trend_period": 55, "pullback_period": 20},
        spreadsheet_ids=("S100",),
        description="Futures pullback trend continuation.",
    ),
    StrategySpec(
        key="futures_outright_trend_following",
        strategy_class=TimeSeriesMomentumStrategy,
        category="futures",
        mode="full",
        params={"lookback": 120, "min_return_pct": 0.05, "trend_filter_period": 60},
        spreadsheet_ids=("S098",),
        description="Outright futures trend-following proxy.",
    ),
    StrategySpec(
        key="precious_metals_breakout_limited",
        strategy_class=PriceChannelBreakoutStrategy,
        category="commodities",
        mode="limited",
        params={"lookback": 40, "direction": "long"},
        spreadsheet_ids=("S114",),
        description="Limited precious-metals safe-haven breakout proxy.",
    ),
    StrategySpec(
        key="fx_trend_following",
        strategy_class=TimeSeriesMomentumStrategy,
        category="forex",
        mode="full",
        params={"lookback": 63, "min_return_pct": 0.02, "trend_filter_period": 50},
        spreadsheet_ids=("S117",),
        description="FX trend-following proxy.",
    ),
    StrategySpec(
        key="fx_breakout_on_macro_data_limited",
        strategy_class=OpeningRangeBreakoutStrategy,
        category="forex",
        mode="limited",
        params={"timezone": "UTC", "session_start": "00:00", "opening_range_minutes": 60},
        spreadsheet_ids=("S118",),
        description="Limited macro-breakout proxy without event feed.",
    ),
    StrategySpec(
        key="fx_range_trading",
        strategy_class=BollingerReversionStrategy,
        category="forex",
        mode="full",
        params={"window": 20, "num_std": 2.0},
        spreadsheet_ids=("S119",),
        description="FX range-trading mean-reversion proxy.",
    ),
    StrategySpec(
        key="fx_mean_reversion",
        strategy_class=BollingerReversionStrategy,
        category="forex",
        mode="full",
        params={"window": 20, "num_std": 2.3},
        spreadsheet_ids=("S120",),
        description="FX swing mean-reversion proxy.",
    ),
    StrategySpec(
        key="london_breakout",
        strategy_class=OpeningRangeBreakoutStrategy,
        category="forex",
        mode="full",
        params={"timezone": "Europe/London", "session_start": "08:00", "opening_range_minutes": 60},
        spreadsheet_ids=("S126",),
        description="London session breakout proxy.",
    ),
    StrategySpec(
        key="asian_range_fade_limited",
        strategy_class=BollingerReversionStrategy,
        category="forex",
        mode="limited",
        params={"window": 30, "num_std": 2.2},
        spreadsheet_ids=("S127",),
        description="Limited Asian range-fade proxy.",
    ),
    StrategySpec(
        key="fx_statistical_pairs_limited",
        strategy_class=PairsZScoreStrategy,
        category="forex",
        mode="limited",
        params={"lookback": 80, "entry_z": 2.0, "exit_z": 0.6},
        spreadsheet_ids=("S129",),
        description="Limited FX statistical pair spread proxy.",
    ),
    StrategySpec(
        key="g10_relative_strength_limited",
        strategy_class=RelativeStrengthRotationStrategy,
        category="forex",
        mode="limited",
        params={"benchmark_col": "benchmark_close", "rs_lookback": 90, "rs_ma_period": 20},
        spreadsheet_ids=("S124",),
        description="Limited G10 relative-strength basket proxy.",
    ),
    StrategySpec(
        key="risk_on_risk_off_fx_basket_limited",
        strategy_class=RelativeStrengthRotationStrategy,
        category="forex",
        mode="limited",
        params={"benchmark_col": "benchmark_close", "rs_lookback": 60, "rs_ma_period": 20},
        spreadsheet_ids=("S123",),
        description="Limited risk-on/risk-off FX basket proxy.",
    ),
    StrategySpec(
        key="crypto_trend_following",
        strategy_class=TimeSeriesMomentumStrategy,
        category="quant",
        mode="full",
        params={"lookback": 90, "min_return_pct": 0.08, "trend_filter_period": 50},
        spreadsheet_ids=("S139",),
        description="Crypto trend-following proxy.",
    ),
    StrategySpec(
        key="crypto_breakout",
        strategy_class=PriceChannelBreakoutStrategy,
        category="quant",
        mode="full",
        params={"lookback": 30},
        spreadsheet_ids=("S140",),
        description="Crypto breakout proxy.",
    ),
    StrategySpec(
        key="crypto_mean_reversion",
        strategy_class=BollingerReversionStrategy,
        category="quant",
        mode="full",
        params={"window": 20, "num_std": 2.5},
        spreadsheet_ids=("S141",),
        description="Crypto mean-reversion proxy.",
    ),
    StrategySpec(
        key="alt_btc_relative_strength_limited",
        strategy_class=RelativeStrengthRotationStrategy,
        category="quant",
        mode="limited",
        params={"benchmark_col": "benchmark_close", "rs_lookback": 45, "rs_ma_period": 15},
        spreadsheet_ids=("S145",),
        description="Limited ALT/BTC relative-strength proxy.",
    ),
    StrategySpec(
        key="cointegration_pairs_limited",
        strategy_class=PairsZScoreStrategy,
        category="relative_value",
        mode="limited",
        params={"lookback": 100, "entry_z": 2.0, "exit_z": 0.5},
        spreadsheet_ids=("S149",),
        description="Limited cointegration pair proxy using static spread z-score.",
    ),
)

_SPEC_BY_KEY: dict[str, StrategySpec] = {spec.key: spec for spec in _SPECS}
_ALIAS_TO_KEY: dict[str, str] = {}
for spec in _SPECS:
    for alias in spec.aliases:
        _ALIAS_TO_KEY[alias] = spec.key

_MANIFEST_PATH = Path(__file__).resolve().parent / "strategy_manifest.json"


def _normalize_name(name: str) -> str:
    return str(name).strip().lower()


def _resolve_key(name: str) -> str:
    key = _normalize_name(name)
    if key in _SPEC_BY_KEY:
        return key
    if key in _ALIAS_TO_KEY:
        return _ALIAS_TO_KEY[key]
    available = ", ".join(sorted(_SPEC_BY_KEY.keys()))
    raise ValueError(f"Unknown strategy '{name}'. Available strategies: {available}")


def get_strategy_registry() -> dict[str, StrategyClass]:
    """Return canonical strategy registry for legacy compatibility."""
    return {key: spec.strategy_class for key, spec in _SPEC_BY_KEY.items()}


def get_strategy_catalog() -> dict[str, dict[str, Any]]:
    """Return enriched metadata for all runnable strategies."""
    return {key: spec.as_catalog_entry() for key, spec in _SPEC_BY_KEY.items()}


def get_runtime_strategy_registry() -> dict[str, dict[str, Any]]:
    """Return runtime-ready registry entries: class + default params + metadata."""
    return {key: spec.as_runtime_entry() for key, spec in _SPEC_BY_KEY.items()}


def list_strategy_keys(category: str | None = None, *, include_aliases: bool = False) -> list[str]:
    """List canonical strategy keys, optionally filtered by category."""
    keys = [
        spec.key
        for spec in _SPECS
        if category is None or spec.category == category
    ]
    if include_aliases:
        keys.extend(sorted(_ALIAS_TO_KEY.keys()))
    return sorted(keys)


def get_strategies_by_category() -> dict[str, list[str]]:
    """Group canonical strategy keys by category."""
    grouped: dict[str, list[str]] = {}
    for spec in _SPECS:
        grouped.setdefault(spec.category, []).append(spec.key)
    for key in list(grouped.keys()):
        grouped[key] = sorted(grouped[key])
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def get_strategy_class(name: str) -> StrategyClass:
    """Resolve a strategy class by canonical key or alias."""
    return _SPEC_BY_KEY[_resolve_key(name)].strategy_class


def get_strategy_defaults(name: str) -> dict[str, Any]:
    """Return default parameters for the given strategy key or alias."""
    return dict(_SPEC_BY_KEY[_resolve_key(name)].params)


def get_strategy_spec(name: str) -> StrategySpec:
    """Return full strategy spec for key or alias."""
    return _SPEC_BY_KEY[_resolve_key(name)]


def create_strategy(
    name: str,
    *,
    params: dict[str, Any] | None = None,
) -> BaseStrategy:
    """
    Instantiate a registered strategy with merged default + override params.

    Initialization is called so the returned object is immediately runnable.
    """
    spec = get_strategy_spec(name)
    merged_params = dict(spec.params)
    if params:
        merged_params.update(params)
    instance = spec.strategy_class(**merged_params)
    instance.initialize(merged_params)
    return instance


@lru_cache(maxsize=1)
def load_strategy_manifest() -> dict[str, Any]:
    """Load the spreadsheet-backed strategy support manifest."""
    if not _MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"strategy manifest is missing at '{_MANIFEST_PATH.as_posix()}'"
        )
    with _MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("strategy manifest must be a JSON object")
    return payload


def list_manifest_entries(classification: str | None = None) -> list[dict[str, Any]]:
    """List manifest entries, optionally filtered by classification."""
    manifest = load_strategy_manifest()
    rows = list(manifest.get("strategies", []))
    if classification is None:
        return rows
    clean = str(classification).strip().lower()
    return [row for row in rows if str(row.get("classification", "")).lower() == clean]


def list_unsupported_strategies() -> list[dict[str, Any]]:
    """Return deferred + non-strategy-layer rows from manifest."""
    return [
        row
        for row in list_manifest_entries()
        if row.get("classification") in {"deferred", "not_strategy_layer"}
    ]

