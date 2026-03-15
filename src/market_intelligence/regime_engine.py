"""
Provider-agnostic composite market regime engine.

Design
------
This module is the *thin orchestration layer* that ties together two existing,
production-ready components:

  1. RegimeDetector  (src.monitoring.regime_detector)
     - Fast approach: MA crossover (fast=20, slow=50) + daily-return std-dev
     - Output: RegimeState (BULLISH / BEARISH / RANGEBOUND /
               HIGH_VOLATILITY / LOW_VOLATILITY / UNKNOWN)

  2. VolatilityRegimeAnalyzer  (src.market_intelligence.volatility_regime)
     - More precise: realized-vol (annualized) + ATR dynamics
     - Output: VolatilityRegimeType (LOW / EXPANDING / HIGH /
               CONTRACTION / UNKNOWN)

Both detectors accept a DataHandler wrapping a clean OHLCV DataFrame, so the
engine is provider-agnostic at its core:  just pass any well-formed OHLCV df.

Entry point
-----------
    engine = MarketRegimeEngine()
    snapshot = engine.detect(df, symbol="NIFTY50")
    print(snapshot.composite_regime.value)   # e.g. "bullish_trending"

Composite regime mapping
------------------------
The mapping is deterministic and documented here:

  RegimeState          VolatilityRegimeType   CompositeRegime
  -------              -------                -------
  BULLISH              LOW / CONTRACTION      bullish_trending
  BULLISH              EXPANDING              bullish_trending
  BULLISH              HIGH                   risk_off  (vol spike overrides)
  BULLISH              UNKNOWN                bullish_trending
  BEARISH              LOW / CONTRACTION      bearish_trending
  BEARISH              EXPANDING              bearish_volatile
  BEARISH              HIGH                   risk_off
  BEARISH              UNKNOWN                bearish_trending
  RANGEBOUND           LOW / CONTRACTION      rangebound
  RANGEBOUND           EXPANDING / HIGH       risk_off
  RANGEBOUND           UNKNOWN                rangebound
  HIGH_VOLATILITY      any                    risk_off  (detector already says HOT)
  LOW_VOLATILITY       LOW / CONTRACTION      rangebound
  LOW_VOLATILITY       EXPANDING              bullish_sideways
  LOW_VOLATILITY       HIGH                   risk_off
  LOW_VOLATILITY       UNKNOWN                rangebound
  UNKNOWN              any                    unknown

Trend-state derivation (RegimeState → TrendState):
  BULLISH         → TrendState.BULLISH
  BEARISH         → TrendState.BEARISH
  RANGEBOUND      → TrendState.RANGEBOUND
  HIGH_VOLATILITY → TrendState.UNKNOWN   (trend unclear during stress)
  LOW_VOLATILITY  → TrendState.RANGEBOUND
  UNKNOWN         → TrendState.UNKNOWN
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.core.data_handler import DataHandler
from src.market_intelligence.config import VolatilityRegimeConfig
from src.market_intelligence.models import (
    CompositeRegime,
    MarketRegimeSnapshot,
    TrendState,
    VolatilityRegimeType,
)
from src.market_intelligence.volatility_regime import VolatilityRegimeAnalyzer
from src.monitoring.config import RegimeDetectorConfig
from src.monitoring.models import RegimeState
from src.monitoring.regime_detector import RegimeDetector


class MarketRegimeEngineError(Exception):
    """Raised when the regime engine cannot complete detection."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class MarketRegimeEngineConfig:
    """
    Unified config for MarketRegimeEngine.

    Wraps the two underlying detector configs so the caller can tune
    every threshold from one place without touching regime_detector.py
    or volatility_regime.py.

    Attributes
    ----------
    symbol : str
        Label embedded in the MarketRegimeSnapshot (e.g. "NIFTY50").
        Does not affect the calculation.
    long_ma_period : int
        Period for the supplementary long-term moving average (default 200).
        This MA is *not* used in the classification logic; it is included in
        the snapshot as an informational metric.
    trend : RegimeDetectorConfig
        Configuration passed to RegimeDetector.detect().
    volatility : VolatilityRegimeConfig
        Configuration passed to VolatilityRegimeAnalyzer.detect().
    require_min_bars : bool
        If True (default) and the DataFrame has fewer bars than the minimum
        required by both detectors, raise MarketRegimeEngineError instead of
        returning UNKNOWN.
    """

    symbol:           str                   = "NIFTY50"
    long_ma_period:   int                   = 200
    trend:            RegimeDetectorConfig  = field(default_factory=RegimeDetectorConfig)
    volatility:       VolatilityRegimeConfig = field(default_factory=VolatilityRegimeConfig)
    require_min_bars: bool                  = False   # lenient by default; returns UNKNOWN

    def __post_init__(self) -> None:
        if self.long_ma_period < 2:
            raise ValueError("long_ma_period must be >= 2")


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class MarketRegimeEngine:
    """
    Provider-agnostic composite market regime engine.

    Usage
    -----
        engine  = MarketRegimeEngine()
        df      = ...  # OHLCV DataFrame with index=timestamp
        snapshot = engine.detect(df, symbol="NIFTY50")

    The engine is stateless: each call to detect() is independent.
    It can be called repeatedly with different DataFrames.
    """

    _trend_detector: RegimeDetector          = field(default_factory=RegimeDetector, init=False)
    _vol_analyzer:   VolatilityRegimeAnalyzer = field(default_factory=VolatilityRegimeAnalyzer, init=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        df: pd.DataFrame,
        config: Optional[MarketRegimeEngineConfig] = None,
        symbol: Optional[str] = None,
    ) -> MarketRegimeSnapshot:
        """
        Run full regime detection on a clean OHLCV DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Historical OHLCV data.  Must have columns:
            open, high, low, close, volume.
            Index should be a DatetimeIndex or timestamp-compatible index.
        config : MarketRegimeEngineConfig, optional
            Full configuration.  Defaults are used if not provided.
        symbol : str, optional
            Override the symbol label from config (handy for one-off calls).

        Returns
        -------
        MarketRegimeSnapshot
            Composite result.  Never raises on ordinary data issues —
            returns regime=UNKNOWN with a populated `reason` field instead,
            unless config.require_min_bars=True.

        Raises
        ------
        MarketRegimeEngineError
            Only if config.require_min_bars=True and data is insufficient.
        """
        cfg = config or MarketRegimeEngineConfig()
        label = symbol or cfg.symbol

        # --- Schema validation -------------------------------------------------
        required_cols = {"open", "high", "low", "close", "volume"}
        missing = required_cols - set(df.columns)
        if missing:
            raise MarketRegimeEngineError(
                f"Input DataFrame is missing required columns: {sorted(missing)}"
            )
        if df.empty:
            raise MarketRegimeEngineError("Input DataFrame is empty.")

        # --- Minimum bar check ------------------------------------------------
        min_bars = max(
            cfg.trend.trend_slow_period + cfg.trend.volatility_period + 1,
            cfg.volatility.atr_baseline_period + cfg.volatility.realized_vol_window + 2,
        )
        warnings: list[str] = []

        if len(df) < min_bars:
            msg = (
                f"Only {len(df)} bars available; need >= {min_bars} for full detection."
            )
            if cfg.require_min_bars:
                raise MarketRegimeEngineError(msg)
            warnings.append(msg)
            return self._unknown_snapshot(label, df, warnings, msg)

        dh = DataHandler(df)

        # --- Trend regime (RegimeDetector) ------------------------------------
        try:
            trend_assess = self._trend_detector.detect(dh, cfg.trend, label)
        except Exception as exc:
            warnings.append(f"RegimeDetector failed: {exc}")
            return self._unknown_snapshot(label, df, warnings, f"trend detection error: {exc}")

        # --- Volatility regime (VolatilityRegimeAnalyzer) ---------------------
        vol_snap = None
        vol_regime = VolatilityRegimeType.UNKNOWN
        try:
            vol_snap = self._vol_analyzer.detect(label, dh, cfg.volatility)
            vol_regime = vol_snap.regime
        except Exception as exc:
            warnings.append(f"VolatilityRegimeAnalyzer failed: {exc}")

        # --- Long-term MA (informational, does not affect classification) ------
        long_ma: Optional[float] = None
        if len(df) >= cfg.long_ma_period:
            lma_series = df["close"].astype(float).rolling(
                cfg.long_ma_period, min_periods=cfg.long_ma_period
            ).mean()
            val = lma_series.iloc[-1]
            if pd.notna(val):
                long_ma = float(val)
        else:
            warnings.append(
                f"Not enough bars for {cfg.long_ma_period}-MA "
                f"({len(df)} < {cfg.long_ma_period}); long_ma set to None."
            )

        # --- Derive TrendState ------------------------------------------------
        trend_state = self._trend_state(trend_assess.regime)

        # --- Compute composite regime -----------------------------------------
        composite = self._composite(trend_assess.regime, vol_regime)

        # --- Extract numeric metrics ------------------------------------------
        fast_ma: Optional[float] = None
        slow_ma: Optional[float] = None
        close_series = df["close"].astype(float)
        fma = close_series.rolling(cfg.trend.trend_fast_period, min_periods=cfg.trend.trend_fast_period).mean()
        sma = close_series.rolling(cfg.trend.trend_slow_period, min_periods=cfg.trend.trend_slow_period).mean()
        if pd.notna(fma.iloc[-1]):
            fast_ma = float(fma.iloc[-1])
        if pd.notna(sma.iloc[-1]):
            slow_ma = float(sma.iloc[-1])

        last_close = float(close_series.iloc[-1])
        timestamp = pd.Timestamp(df.index[-1])

        reason_parts = [trend_assess.reason]
        if vol_snap is not None:
            reason_parts.append(
                f"vol_regime={vol_snap.regime.value}, "
                f"realized_vol={vol_snap.realized_volatility:.4f}, "
                f"atr_ratio={vol_snap.atr_ratio:.4f}"
            )
        reason = " | ".join(p for p in reason_parts if p)

        return MarketRegimeSnapshot(
            symbol=label,
            timestamp=timestamp,
            trend_regime=trend_assess.regime,
            trend_state=trend_state,
            volatility_regime=vol_regime,
            composite_regime=composite,
            trend_score=trend_assess.trend_score,
            volatility_score=trend_assess.volatility_score,
            vol_state_score=vol_snap.state_score if vol_snap else None,
            realized_volatility=vol_snap.realized_volatility if vol_snap else None,
            atr_value=vol_snap.atr_value if vol_snap else None,
            atr_ratio=vol_snap.atr_ratio if vol_snap else None,
            fast_ma=fast_ma,
            slow_ma=slow_ma,
            long_ma=long_ma,
            last_close=last_close,
            bars_used=len(df),
            reason=reason,
            warnings=warnings,
            metadata={"based_on": "dataframe"},
        )

    # ------------------------------------------------------------------
    # Classification helpers (pure-static, documented, easy to tune)
    # ------------------------------------------------------------------

    @staticmethod
    def _trend_state(regime: RegimeState) -> TrendState:
        """Map Phase-4 RegimeState → simplified TrendState."""
        mapping = {
            RegimeState.BULLISH:         TrendState.BULLISH,
            RegimeState.BEARISH:         TrendState.BEARISH,
            RegimeState.RANGEBOUND:      TrendState.RANGEBOUND,
            RegimeState.HIGH_VOLATILITY: TrendState.UNKNOWN,    # trend is noise in stress
            RegimeState.LOW_VOLATILITY:  TrendState.RANGEBOUND, # sideways, minimal momentum
            RegimeState.UNKNOWN:         TrendState.UNKNOWN,
        }
        return mapping.get(regime, TrendState.UNKNOWN)

    @staticmethod
    def _composite(
        trend_regime: RegimeState,
        vol_regime: VolatilityRegimeType,
    ) -> CompositeRegime:
        """
        Deterministic 2-D mapping: (RegimeState, VolatilityRegimeType) → CompositeRegime.

        Rule hierarchy (highest priority first):
        1. RegimeState.HIGH_VOLATILITY  → always RISK_OFF
           (RegimeDetector already detected high daily-return std dev)
        2. VolatilityRegimeType.HIGH    → always RISK_OFF
           (realized vol + ATR both screaming high)
        3. BULLISH + low/calm vol       → BULLISH_TRENDING
        4. BULLISH + expanding vol      → BULLISH_TRENDING  (trend still intact)
        5. BEARISH + expanding/high vol → BEARISH_VOLATILE
        6. BEARISH + calm vol           → BEARISH_TRENDING
        7. RANGEBOUND + expanding vol   → RISK_OFF  (no trend, vol spike = unsafe)
        8. RANGEBOUND / LOW_VOL + calm  → RANGEBOUND
        9. LOW_VOL + expanding          → BULLISH_SIDEWAYS  (rare: flat trend, rising vol)
        10. Anything UNKNOWN            → UNKNOWN
        """
        # Priority 1 & 2: unconditional RISK_OFF when volatility is stressed
        if trend_regime == RegimeState.HIGH_VOLATILITY:
            return CompositeRegime.RISK_OFF
        if vol_regime == VolatilityRegimeType.HIGH:
            return CompositeRegime.RISK_OFF

        if trend_regime == RegimeState.UNKNOWN:
            return CompositeRegime.UNKNOWN

        # --- Bullish trend ---
        if trend_regime == RegimeState.BULLISH:
            # All non-HIGH vol states are safe for longs in a bull trend
            return CompositeRegime.BULLISH_TRENDING

        # --- Bearish trend ---
        if trend_regime == RegimeState.BEARISH:
            if vol_regime in (VolatilityRegimeType.EXPANDING,):
                return CompositeRegime.BEARISH_VOLATILE
            return CompositeRegime.BEARISH_TRENDING

        # --- Rangebound ---
        if trend_regime == RegimeState.RANGEBOUND:
            if vol_regime == VolatilityRegimeType.EXPANDING:
                # Range with expanding vol: breakout watch but not risk_off
                # unless vol spikes to HIGH (already handled above)
                return CompositeRegime.RANGEBOUND
            return CompositeRegime.RANGEBOUND

        # --- Low-volatility (no strong trend direction) ---
        if trend_regime == RegimeState.LOW_VOLATILITY:
            if vol_regime == VolatilityRegimeType.EXPANDING:
                # Compressed range starting to expand — often pre-breakout
                return CompositeRegime.BULLISH_SIDEWAYS
            return CompositeRegime.RANGEBOUND

        return CompositeRegime.UNKNOWN

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _unknown_snapshot(
        symbol: str,
        df: pd.DataFrame,
        warnings: list[str],
        reason: str,
    ) -> MarketRegimeSnapshot:
        """Return a safe UNKNOWN snapshot when detection cannot complete."""
        ts = pd.Timestamp(df.index[-1]) if not df.empty else pd.Timestamp.now(tz="UTC")
        last_close: Optional[float] = None
        if not df.empty and "close" in df.columns:
            last_close = float(df["close"].iloc[-1])
        return MarketRegimeSnapshot(
            symbol=symbol,
            timestamp=ts,
            trend_regime=RegimeState.UNKNOWN,
            trend_state=TrendState.UNKNOWN,
            volatility_regime=VolatilityRegimeType.UNKNOWN,
            composite_regime=CompositeRegime.UNKNOWN,
            last_close=last_close,
            bars_used=len(df),
            reason=reason,
            warnings=warnings,
            metadata={"based_on": "unknown_fallback"},
        )
