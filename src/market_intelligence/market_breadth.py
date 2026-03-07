"""
Market breadth analytics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.core.data_handler import DataHandler
from src.market_intelligence.config import BreadthConfig
from src.market_intelligence.models import BreadthMetrics, BreadthSnapshot, BreadthState


class MarketBreadthError(Exception):
    """Raised when breadth analysis cannot be computed."""


@dataclass
class MarketBreadthAnalyzer:
    def analyze(
        self,
        data_by_symbol: dict[str, DataHandler],
        config: BreadthConfig,
        benchmark_symbol: str | None = None,
    ) -> BreadthSnapshot:
        if not data_by_symbol:
            metrics = BreadthMetrics(
                advancing_count=0,
                declining_count=0,
                unchanged_count=0,
                ad_ratio=0.0,
                ad_line=0.0,
                pct_above_ma=0.0,
                pct_new_highs=0.0,
                pct_new_lows=0.0,
                universe_size=0,
            )
            return BreadthSnapshot(
                timestamp=pd.Timestamp.now(tz="UTC"),
                timeframe=config.timeframe,
                metrics=metrics,
                breadth_state=BreadthState.UNKNOWN,
                benchmark_symbol=benchmark_symbol,
                metadata={"reason": "empty_universe"},
            )

        advancing = 0
        declining = 0
        unchanged = 0
        above_ma = 0
        new_highs = 0
        new_lows = 0
        valid_symbols = 0
        latest_timestamps: list[pd.Timestamp] = []

        for symbol, dh in data_by_symbol.items():
            df = dh.data
            if "close" not in df.columns or len(df) < 2:
                continue

            close = df["close"].astype(float)
            valid_symbols += 1
            latest_timestamps.append(pd.Timestamp(df.index[-1]))

            latest = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            if latest > prev:
                advancing += 1
            elif latest < prev:
                declining += 1
            else:
                unchanged += 1

            if len(close) >= config.moving_average_period:
                ma = close.rolling(config.moving_average_period, min_periods=config.moving_average_period).mean().iloc[-1]
                if pd.notna(ma) and latest > float(ma):
                    above_ma += 1

            lookback = min(len(close), config.new_high_low_lookback)
            window = close.tail(lookback)
            if len(window) > 0:
                if latest >= float(window.max()):
                    new_highs += 1
                if latest <= float(window.min()):
                    new_lows += 1

        if valid_symbols == 0:
            raise MarketBreadthError("No valid symbols with minimum bars for breadth analysis")

        if declining == 0:
            ad_ratio = float("inf") if advancing > 0 else 0.0
        else:
            ad_ratio = advancing / declining

        ad_line = self._compute_ad_line(data_by_symbol, config.ad_line_lookback)

        pct_above_ma = (above_ma / valid_symbols) * 100.0
        pct_new_highs = (new_highs / valid_symbols) * 100.0
        pct_new_lows = (new_lows / valid_symbols) * 100.0

        state = self._classify_state(
            ad_ratio=ad_ratio,
            pct_above_ma=pct_above_ma,
            config=config,
        )

        metrics = BreadthMetrics(
            advancing_count=advancing,
            declining_count=declining,
            unchanged_count=unchanged,
            ad_ratio=ad_ratio if np.isfinite(ad_ratio) else 999.0,
            ad_line=float(ad_line),
            pct_above_ma=float(pct_above_ma),
            pct_new_highs=float(pct_new_highs),
            pct_new_lows=float(pct_new_lows),
            universe_size=valid_symbols,
            metadata={"raw_ad_ratio": ad_ratio},
        )

        timestamp = max(latest_timestamps) if latest_timestamps else pd.Timestamp.now(tz="UTC")
        return BreadthSnapshot(
            timestamp=timestamp,
            timeframe=config.timeframe,
            metrics=metrics,
            breadth_state=state,
            benchmark_symbol=benchmark_symbol,
        )

    @staticmethod
    def _compute_ad_line(data_by_symbol: dict[str, DataHandler], lookback: int) -> float:
        if lookback < 2:
            return 0.0

        changes: list[pd.Series] = []
        for dh in data_by_symbol.values():
            df = dh.data
            if "close" not in df.columns or len(df) < 2:
                continue
            close = df["close"].astype(float).tail(lookback + 1)
            diff = close.diff().dropna()
            signs = diff.apply(lambda x: 1.0 if x > 0 else (-1.0 if x < 0 else 0.0))
            changes.append(signs)

        if not changes:
            return 0.0

        aligned = pd.concat(changes, axis=1).fillna(0.0)
        breadth_daily = aligned.sum(axis=1)
        ad_line_series = breadth_daily.cumsum()
        return float(ad_line_series.iloc[-1]) if len(ad_line_series) > 0 else 0.0

    @staticmethod
    def _classify_state(ad_ratio: float, pct_above_ma: float, config: BreadthConfig) -> BreadthState:
        ratio = 999.0 if not np.isfinite(ad_ratio) else ad_ratio
        if (
            ratio >= config.strong_ad_ratio_threshold
            and pct_above_ma >= config.strong_pct_above_ma_threshold
        ):
            return BreadthState.STRONG
        if (
            ratio <= config.weak_ad_ratio_threshold
            and pct_above_ma <= config.weak_pct_above_ma_threshold
        ):
            return BreadthState.WEAK
        return BreadthState.NEUTRAL
