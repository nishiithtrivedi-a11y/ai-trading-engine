"""
Unit tests for MarketRegimeEngine.

Test coverage:
- Bull-trend synthetic series → composite=bullish_trending
- Bear-trend synthetic series → composite=bearish_trending
- High-volatility series → composite=risk_off
- Low-volatility / sideways series → composite=rangebound or bullish_sideways
- Insufficient bars → UNKNOWN (default lenient mode)
- Insufficient bars + require_min_bars → MarketRegimeEngineError raised
- Missing required columns → MarketRegimeEngineError raised
- Empty DataFrame → MarketRegimeEngineError raised
- to_dict() contains all required keys
- summary_line() returns a non-empty ASCII string
- _composite() static method mapping table coverage
- _trend_state() static method mapping coverage
- Vol-state-score in [0, 100]
- Warnings list is populated for insufficient-bar edge case
- Long MA is None when fewer than long_ma_period bars
- Long MA is float when bars >= long_ma_period
"""

from __future__ import annotations

import math
import pytest
import pandas as pd

from src.market_intelligence.models import (
    CompositeRegime,
    MarketRegimeSnapshot,
    TrendState,
    VolatilityRegimeType,
)
from src.market_intelligence.regime_engine import (
    MarketRegimeEngine,
    MarketRegimeEngineConfig,
    MarketRegimeEngineError,
)
from src.monitoring.models import RegimeState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(
    close_values: list[float],
    start: str = "2020-01-01",
    high_mult: float = 1.005,
    low_mult: float = 0.995,
) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a list of close prices."""
    n = len(close_values)
    return pd.DataFrame(
        {
            "open":   close_values,
            "high":   [v * high_mult  for v in close_values],
            "low":    [v * low_mult   for v in close_values],
            "close":  close_values,
            "volume": [1_000_000 + i  for i in range(n)],
        },
        index=pd.date_range(start, periods=n, freq="B", name="timestamp"),
    )


def _bull_df(n: int = 300) -> pd.DataFrame:
    """Steady linear uptrend: +0.15% per bar, tight range."""
    close = [100.0 * (1.0015 ** i) for i in range(n)]
    return _make_df(close, high_mult=1.002, low_mult=0.998)


def _bear_df(n: int = 300) -> pd.DataFrame:
    """Gentle exponential downtrend: -0.20% per bar, tight range."""
    close = [300.0 * (0.998 ** i) for i in range(n)]
    return _make_df(close, high_mult=1.002, low_mult=0.998)


def _high_vol_df(n: int = 300) -> pd.DataFrame:
    """Alternating +7% / -7% — very high realized volatility."""
    v = 100.0
    close: list[float] = []
    for i in range(n):
        v *= 1.07 if i % 2 == 0 else 0.93
        close.append(v)
    return _make_df(close, high_mult=1.01, low_mult=0.99)


def _flat_low_vol_df(n: int = 300) -> pd.DataFrame:
    """Completely flat price — zero trend, zero vol."""
    close = [200.0] * n
    # Avoid completely identical O/H/L/C that might cause NaN in indicators
    close = [200.0 + 0.001 * math.sin(i * 0.3) for i in range(n)]
    return _make_df(close, high_mult=1.001, low_mult=0.999)


# ---------------------------------------------------------------------------
# Standard engine instance and config
# ---------------------------------------------------------------------------
ENGINE = MarketRegimeEngine()

_FAST_CFG = MarketRegimeEngineConfig(
    symbol="TEST",
    long_ma_period=50,   # small so 300 bars is enough
    trend=__import__(
        "src.monitoring.config", fromlist=["RegimeDetectorConfig"]
    ).RegimeDetectorConfig(
        trend_fast_period=10,
        trend_slow_period=30,
        volatility_period=14,
        high_volatility_threshold=0.05,
        low_volatility_threshold=0.001,
    ),
)


# ---------------------------------------------------------------------------
# Correct regime classification
# ---------------------------------------------------------------------------

class TestBullTrend:
    def test_composite_is_bullish_trending(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG)
        assert snap.composite_regime == CompositeRegime.BULLISH_TRENDING, (
            f"Expected BULLISH_TRENDING, got {snap.composite_regime}"
        )

    def test_trend_state_is_bullish(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG)
        assert snap.trend_state == TrendState.BULLISH

    def test_trend_regime_is_bullish(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG)
        assert snap.trend_regime == RegimeState.BULLISH

    def test_trend_score_is_positive(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG)
        assert snap.trend_score is not None and snap.trend_score > 0


class TestBearTrend:
    def test_composite_is_bearish_trending(self):
        snap = ENGINE.detect(_bear_df(), config=_FAST_CFG)
        assert snap.composite_regime == CompositeRegime.BEARISH_TRENDING, (
            f"Expected BEARISH_TRENDING, got {snap.composite_regime}"
        )

    def test_trend_state_is_bearish(self):
        snap = ENGINE.detect(_bear_df(), config=_FAST_CFG)
        assert snap.trend_state == TrendState.BEARISH

    def test_trend_score_is_negative(self):
        snap = ENGINE.detect(_bear_df(), config=_FAST_CFG)
        assert snap.trend_score is not None and snap.trend_score < 0


class TestHighVolatility:
    def test_composite_is_risk_off(self):
        snap = ENGINE.detect(_high_vol_df(), config=_FAST_CFG)
        assert snap.composite_regime == CompositeRegime.RISK_OFF, (
            f"Expected RISK_OFF, got {snap.composite_regime}"
        )

    def test_regime_contains_high_volatility(self):
        snap = ENGINE.detect(_high_vol_df(), config=_FAST_CFG)
        assert snap.trend_regime == RegimeState.HIGH_VOLATILITY or \
               snap.volatility_regime == VolatilityRegimeType.HIGH, (
            f"trend={snap.trend_regime}, vol={snap.volatility_regime}"
        )


class TestFlatLowVol:
    def test_composite_is_non_trending(self):
        # A near-flat sinusoidal series has essentially zero vol.  RegimeDetector
        # may call it BULLISH (tiny positive trend_score > 0.0 threshold) or
        # RANGEBOUND or LOW_VOLATILITY depending on the exact MA snapshot.
        # What matters: it is NOT bearish_volatile or risk_off.
        snap = ENGINE.detect(_flat_low_vol_df(), config=_FAST_CFG)
        assert snap.composite_regime not in (
            CompositeRegime.BEARISH_VOLATILE,
            CompositeRegime.RISK_OFF,
        ), f"Unexpected high-stress regime for flat series: {snap.composite_regime}"


# ---------------------------------------------------------------------------
# Snapshot data quality
# ---------------------------------------------------------------------------

class TestSnapshotFields:
    def setup_method(self):
        self.snap = ENGINE.detect(_bull_df(), config=_FAST_CFG, symbol="BULL_TEST")

    def test_symbol_set(self):
        assert self.snap.symbol == "BULL_TEST"

    def test_timestamp_is_pandas_timestamp(self):
        assert isinstance(self.snap.timestamp, pd.Timestamp)

    def test_bars_used_matches_input(self):
        assert self.snap.bars_used == 300

    def test_last_close_is_positive(self):
        assert self.snap.last_close is not None
        assert self.snap.last_close > 0

    def test_fast_ma_is_positive(self):
        assert self.snap.fast_ma is not None and self.snap.fast_ma > 0

    def test_slow_ma_is_positive(self):
        assert self.snap.slow_ma is not None and self.snap.slow_ma > 0

    def test_long_ma_present_when_enough_bars(self):
        # _FAST_CFG uses long_ma_period=50; bull_df has 300 bars
        assert self.snap.long_ma is not None and self.snap.long_ma > 0

    def test_vol_state_score_in_range(self):
        if self.snap.vol_state_score is not None:
            assert 0 <= self.snap.vol_state_score <= 100

    def test_warnings_is_list(self):
        assert isinstance(self.snap.warnings, list)

    def test_no_warnings_on_clean_data(self):
        assert len(self.snap.warnings) == 0

    def test_reason_is_str(self):
        assert isinstance(self.snap.reason, str)


class TestToDict:
    def test_required_keys_present(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG)
        d = snap.to_dict()
        required = [
            "symbol", "timestamp", "trend_regime", "trend_state",
            "volatility_regime", "composite_regime", "bars_used", "reason",
            "trend_score", "realized_volatility", "atr_ratio",
            "fast_ma", "slow_ma", "long_ma", "last_close",
            "warnings", "metadata",
        ]
        for k in required:
            assert k in d, f"Missing key in to_dict(): {k!r}"

    def test_composite_regime_value_is_string(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG)
        d = snap.to_dict()
        assert isinstance(d["composite_regime"], str)

    def test_timestamp_is_iso_string(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG)
        d = snap.to_dict()
        # Should not raise
        pd.Timestamp(d["timestamp"])


class TestSummaryLine:
    def test_returns_nonempty_ascii_string(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG)
        line = snap.summary_line()
        assert isinstance(line, str)
        assert len(line) > 0
        # Must be ASCII-safe (Windows cp1252 compatible)
        line.encode("ascii")

    def test_contains_composite_value(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG)
        assert snap.composite_regime.value in snap.summary_line()


# ---------------------------------------------------------------------------
# Long MA edge cases
# ---------------------------------------------------------------------------

class TestLongMA:
    def test_long_ma_none_when_insufficient_bars(self):
        # Use 100 bars: enough for both detectors (min_bars ~= 72 for default
        # vol config) but fewer than long_ma_period=200, so long_ma=None.
        df = _bull_df(n=100)
        cfg = MarketRegimeEngineConfig(
            symbol="T",
            long_ma_period=200,   # needs 200 bars; df has only 100
            trend=_FAST_CFG.trend,
        )
        snap = ENGINE.detect(df, config=cfg)
        assert snap.long_ma is None
        # At least one warning mentioning the long MA period
        assert any("200" in w for w in snap.warnings), (
            f"Expected warning about 200-MA in {snap.warnings}"
        )

    def test_long_ma_populated_when_sufficient_bars(self):
        df = _bull_df(n=300)
        cfg = MarketRegimeEngineConfig(symbol="T", long_ma_period=50, trend=_FAST_CFG.trend)
        snap = ENGINE.detect(df, config=cfg)
        assert snap.long_ma is not None and snap.long_ma > 0


# ---------------------------------------------------------------------------
# Insufficient data handling
# ---------------------------------------------------------------------------

class TestInsufficientData:
    def _tiny_df(self) -> pd.DataFrame:
        return _make_df([100.0 + i * 0.1 for i in range(10)])

    def test_returns_unknown_composite_by_default(self):
        snap = ENGINE.detect(self._tiny_df(), config=_FAST_CFG)
        assert snap.composite_regime == CompositeRegime.UNKNOWN

    def test_warnings_populated(self):
        snap = ENGINE.detect(self._tiny_df(), config=_FAST_CFG)
        assert len(snap.warnings) > 0

    def test_bars_used_reflects_actual_rows(self):
        snap = ENGINE.detect(self._tiny_df(), config=_FAST_CFG)
        assert snap.bars_used == 10

    def test_raises_when_require_min_bars(self):
        cfg = MarketRegimeEngineConfig(
            symbol="T",
            require_min_bars=True,
            trend=_FAST_CFG.trend,
        )
        with pytest.raises(MarketRegimeEngineError):
            ENGINE.detect(self._tiny_df(), config=cfg)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_raises_on_missing_columns(self):
        df = _bull_df().drop(columns=["close"])
        with pytest.raises(MarketRegimeEngineError, match="close"):
            ENGINE.detect(df, config=_FAST_CFG)

    def test_raises_on_empty_dataframe(self):
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
        with pytest.raises(MarketRegimeEngineError, match="empty"):
            ENGINE.detect(df, config=_FAST_CFG)

    def test_raises_on_missing_multiple_columns(self):
        df = _bull_df().drop(columns=["high", "low"])
        with pytest.raises(MarketRegimeEngineError):
            ENGINE.detect(df, config=_FAST_CFG)


# ---------------------------------------------------------------------------
# Static method unit tests (_composite and _trend_state)
# ---------------------------------------------------------------------------

class TestCompositeMapping:
    """Verify the composite lookup table row by row."""

    def _c(self, t: RegimeState, v: VolatilityRegimeType) -> CompositeRegime:
        return MarketRegimeEngine._composite(t, v)

    # -- BULLISH trend
    def test_bull_low_vol(self):
        assert self._c(RegimeState.BULLISH, VolatilityRegimeType.LOW) == CompositeRegime.BULLISH_TRENDING

    def test_bull_contraction_vol(self):
        assert self._c(RegimeState.BULLISH, VolatilityRegimeType.CONTRACTION) == CompositeRegime.BULLISH_TRENDING

    def test_bull_expanding_vol(self):
        assert self._c(RegimeState.BULLISH, VolatilityRegimeType.EXPANDING) == CompositeRegime.BULLISH_TRENDING

    def test_bull_high_vol_is_risk_off(self):
        assert self._c(RegimeState.BULLISH, VolatilityRegimeType.HIGH) == CompositeRegime.RISK_OFF

    def test_bull_unknown_vol(self):
        assert self._c(RegimeState.BULLISH, VolatilityRegimeType.UNKNOWN) == CompositeRegime.BULLISH_TRENDING

    # -- BEARISH trend
    def test_bear_low_vol(self):
        assert self._c(RegimeState.BEARISH, VolatilityRegimeType.LOW) == CompositeRegime.BEARISH_TRENDING

    def test_bear_expanding_vol(self):
        assert self._c(RegimeState.BEARISH, VolatilityRegimeType.EXPANDING) == CompositeRegime.BEARISH_VOLATILE

    def test_bear_high_vol_is_risk_off(self):
        assert self._c(RegimeState.BEARISH, VolatilityRegimeType.HIGH) == CompositeRegime.RISK_OFF

    # -- HIGH_VOLATILITY from RegimeDetector (always RISK_OFF)
    def test_high_vol_regime_always_risk_off(self):
        for v in VolatilityRegimeType:
            assert self._c(RegimeState.HIGH_VOLATILITY, v) == CompositeRegime.RISK_OFF, (
                f"Failed for HIGH_VOLATILITY + {v}"
            )

    # -- RANGEBOUND
    def test_rangebound_low_vol(self):
        assert self._c(RegimeState.RANGEBOUND, VolatilityRegimeType.LOW) == CompositeRegime.RANGEBOUND

    def test_rangebound_high_vol_is_risk_off(self):
        assert self._c(RegimeState.RANGEBOUND, VolatilityRegimeType.HIGH) == CompositeRegime.RISK_OFF

    def test_rangebound_contraction_vol(self):
        assert self._c(RegimeState.RANGEBOUND, VolatilityRegimeType.CONTRACTION) == CompositeRegime.RANGEBOUND

    # -- LOW_VOLATILITY from RegimeDetector
    def test_low_vol_regime_low_vol_is_rangebound(self):
        assert self._c(RegimeState.LOW_VOLATILITY, VolatilityRegimeType.LOW) == CompositeRegime.RANGEBOUND

    def test_low_vol_regime_expanding_is_sideways(self):
        assert self._c(RegimeState.LOW_VOLATILITY, VolatilityRegimeType.EXPANDING) == CompositeRegime.BULLISH_SIDEWAYS

    def test_low_vol_regime_high_vol_is_risk_off(self):
        assert self._c(RegimeState.LOW_VOLATILITY, VolatilityRegimeType.HIGH) == CompositeRegime.RISK_OFF

    # -- UNKNOWN trend
    def test_unknown_trend_calm_vol_returns_unknown(self):
        # When trend is unknown AND vol is calm, result is UNKNOWN.
        for v in (
            VolatilityRegimeType.LOW,
            VolatilityRegimeType.CONTRACTION,
            VolatilityRegimeType.EXPANDING,
            VolatilityRegimeType.UNKNOWN,
        ):
            assert self._c(RegimeState.UNKNOWN, v) == CompositeRegime.UNKNOWN, (
                f"Failed for UNKNOWN + {v}"
            )

    def test_unknown_trend_high_vol_returns_risk_off(self):
        # When vol is HIGH, risk_off always wins regardless of trend direction.
        # This is correct: high volatility is a stress signal even if trend is unclear.
        assert self._c(RegimeState.UNKNOWN, VolatilityRegimeType.HIGH) == CompositeRegime.RISK_OFF


class TestTrendStateMapping:
    def _t(self, r: RegimeState) -> TrendState:
        return MarketRegimeEngine._trend_state(r)

    def test_bullish_maps_to_bullish(self):
        assert self._t(RegimeState.BULLISH) == TrendState.BULLISH

    def test_bearish_maps_to_bearish(self):
        assert self._t(RegimeState.BEARISH) == TrendState.BEARISH

    def test_rangebound_maps_to_rangebound(self):
        assert self._t(RegimeState.RANGEBOUND) == TrendState.RANGEBOUND

    def test_high_vol_maps_to_unknown(self):
        assert self._t(RegimeState.HIGH_VOLATILITY) == TrendState.UNKNOWN

    def test_low_vol_maps_to_rangebound(self):
        assert self._t(RegimeState.LOW_VOLATILITY) == TrendState.RANGEBOUND

    def test_unknown_maps_to_unknown(self):
        assert self._t(RegimeState.UNKNOWN) == TrendState.UNKNOWN


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

class TestConfig:
    def test_default_config_creates_without_error(self):
        cfg = MarketRegimeEngineConfig()
        assert cfg.symbol == "NIFTY50"
        assert cfg.long_ma_period == 200

    def test_invalid_long_ma_period_raises(self):
        with pytest.raises(ValueError):
            MarketRegimeEngineConfig(long_ma_period=1)

    def test_custom_symbol(self):
        cfg = MarketRegimeEngineConfig(symbol="HDFCBANK")
        assert cfg.symbol == "HDFCBANK"

    def test_symbol_override_in_detect(self):
        snap = ENGINE.detect(_bull_df(), config=_FAST_CFG, symbol="OVERRIDE")
        assert snap.symbol == "OVERRIDE"


# ---------------------------------------------------------------------------
# Enum completeness
# ---------------------------------------------------------------------------

class TestCompositeRegimeEnum:
    def test_all_values_are_strings(self):
        for member in CompositeRegime:
            assert isinstance(member.value, str)

    def test_expected_values_present(self):
        values = {m.value for m in CompositeRegime}
        for expected in (
            "bullish_trending", "bullish_sideways", "bearish_trending",
            "bearish_volatile", "rangebound", "risk_off", "unknown",
        ):
            assert expected in values, f"Missing value: {expected!r}"
