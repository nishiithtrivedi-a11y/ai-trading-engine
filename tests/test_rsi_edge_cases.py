"""
Regression tests for BaseStrategy.rsi() edge-case guard rails.

Phase 16A added deterministic handling for degenerate RSI inputs:
  - pure-gain series (avg_loss == 0)  → RSI approaches 100
  - pure-loss series (avg_gain == 0)  → RSI approaches 0
  - completely flat series (both == 0) → RSI approaches 50

These tests lock in that behaviour so it cannot silently regress.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategies.base_strategy import BaseStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PERIOD = 14


def _rsi(prices: list[float]) -> pd.Series:
    return BaseStrategy.rsi(pd.Series(prices, dtype=float), period=PERIOD)


def _last_valid(series: pd.Series) -> float:
    """Return the last non-NaN value in the series."""
    valid = series.dropna()
    assert len(valid) > 0, "Series has no valid (non-NaN) values"
    return float(valid.iloc[-1])


# ---------------------------------------------------------------------------
# Tests — pure gain (avg_loss == 0)
# ---------------------------------------------------------------------------

class TestRsiPureGain:

    def test_pure_rising_prices_gives_rsi_near_100(self):
        # Prices that only ever go up: every delta is positive, avg_loss stays 0
        prices = list(range(100, 130))  # 100, 101, ..., 129 — 30 bars
        result = _rsi(prices)
        last = _last_valid(result)
        assert last == pytest.approx(100.0, abs=1.0), (
            f"Pure gain series should give RSI ~ 100, got {last:.2f}"
        )

    def test_pure_gain_rsi_is_not_nan_or_inf(self):
        prices = list(range(50, 80))
        result = _rsi(prices)
        last = _last_valid(result)
        assert np.isfinite(last), f"RSI should be finite, got {last}"

    def test_pure_gain_rsi_is_exactly_100(self):
        # After warmup the mask rule fires: avg_loss==0 and avg_gain>0 → RSI=100.0
        prices = list(range(100, 120))
        result = _rsi(prices)
        # Check any post-warmup value
        valid = result.dropna()
        assert all(v == pytest.approx(100.0, abs=0.01) for v in valid), (
            "All post-warmup RSI values should be 100.0 for a pure-gain series"
        )


# ---------------------------------------------------------------------------
# Tests — pure loss (avg_gain == 0)
# ---------------------------------------------------------------------------

class TestRsiPureLoss:

    def test_pure_falling_prices_gives_rsi_near_0(self):
        prices = list(range(129, 99, -1))  # 129, 128, ..., 100 — 30 bars
        result = _rsi(prices)
        last = _last_valid(result)
        assert last == pytest.approx(0.0, abs=1.0), (
            f"Pure loss series should give RSI ~ 0, got {last:.2f}"
        )

    def test_pure_loss_rsi_is_not_nan_or_inf(self):
        prices = list(range(79, 49, -1))
        result = _rsi(prices)
        last = _last_valid(result)
        assert np.isfinite(last), f"RSI should be finite, got {last}"

    def test_pure_loss_rsi_is_exactly_0(self):
        prices = list(range(119, 99, -1))
        result = _rsi(prices)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=0.01) for v in valid), (
            "All post-warmup RSI values should be 0.0 for a pure-loss series"
        )


# ---------------------------------------------------------------------------
# Tests — flat (both avg_gain and avg_loss == 0)
# ---------------------------------------------------------------------------

class TestRsiFlatSeries:

    def test_flat_prices_gives_rsi_near_50(self):
        prices = [100.0] * 30
        result = _rsi(prices)
        last = _last_valid(result)
        assert last == pytest.approx(50.0, abs=1.0), (
            f"Flat series should give RSI ~ 50, got {last:.2f}"
        )

    def test_flat_series_rsi_is_not_nan_or_inf(self):
        prices = [200.0] * 30
        result = _rsi(prices)
        last = _last_valid(result)
        assert np.isfinite(last), f"RSI should be finite for flat prices, got {last}"

    def test_flat_series_rsi_is_exactly_50(self):
        prices = [100.0] * 30
        result = _rsi(prices)
        valid = result.dropna()
        assert all(v == pytest.approx(50.0, abs=0.01) for v in valid), (
            "All post-warmup RSI values should be 50.0 for a flat series"
        )


# ---------------------------------------------------------------------------
# Tests — normal mixed series (sanity check the guard rails don't break normal behaviour)
# ---------------------------------------------------------------------------

class TestRsiNormalBehaviour:

    def test_oversold_region_below_30(self):
        # A sharp sell-off: prices drop significantly creating a low RSI
        np.random.seed(42)
        prices = [100.0]
        for _ in range(40):
            prices.append(prices[-1] * np.random.uniform(0.97, 0.99))
        result = _rsi(prices)
        last = _last_valid(result)
        assert last < 30.0, f"After sustained sell-off RSI should be < 30, got {last:.2f}"

    def test_overbought_region_above_70(self):
        # A sustained rally: prices rise significantly creating a high RSI
        np.random.seed(42)
        prices = [100.0]
        for _ in range(40):
            prices.append(prices[-1] * np.random.uniform(1.01, 1.03))
        result = _rsi(prices)
        last = _last_valid(result)
        assert last > 70.0, f"After sustained rally RSI should be > 70, got {last:.2f}"

    def test_rsi_bounded_between_0_and_100(self):
        np.random.seed(0)
        prices = [100.0]
        for _ in range(100):
            prices.append(max(1.0, prices[-1] + np.random.randn() * 5))
        result = _rsi(prices)
        valid = result.dropna()
        assert (valid >= 0.0).all(), "RSI should never be negative"
        assert (valid <= 100.0).all(), "RSI should never exceed 100"

    def test_rsi_warmup_period_produces_nan(self):
        prices = list(range(100, 130))
        result = _rsi(prices)
        # Bars 0 through PERIOD-2 are NaN (insufficient data to compute avg gain/loss).
        # Bar PERIOD-1 is the first valid RSI value (needs exactly PERIOD bars).
        assert result.iloc[:PERIOD - 1].isna().all(), (
            "RSI should be NaN for the first PERIOD-1 bars (warmup)"
        )
        assert not pd.isna(result.iloc[PERIOD - 1]), (
            "RSI should be valid at bar PERIOD-1"
        )

    def test_rsi_returns_series_of_same_length(self):
        prices = list(range(100, 140))
        result = _rsi(prices)
        assert len(result) == len(prices)
