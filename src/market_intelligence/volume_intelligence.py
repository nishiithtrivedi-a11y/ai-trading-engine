"""
Volume intelligence analytics.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.core.data_handler import DataHandler
from src.market_intelligence.config import VolumeIntelligenceConfig
from src.market_intelligence.models import (
    VolumeAnalysisSnapshot,
    VolumeSignal,
    VolumeSignalType,
)


class VolumeIntelligenceError(Exception):
    """Raised when volume intelligence analysis fails."""


@dataclass
class VolumeIntelligenceAnalyzer:
    def analyze_symbol(
        self,
        symbol: str,
        data_handler: DataHandler,
        config: VolumeIntelligenceConfig,
    ) -> VolumeAnalysisSnapshot:
        df = data_handler.data
        required = {"close", "volume"}
        if not required.issubset(set(df.columns)):
            raise VolumeIntelligenceError(
                f"Missing required columns for {symbol}: {sorted(required - set(df.columns))}"
            )

        if len(df) < max(config.spike_lookback, config.accumulation_window, config.vw_momentum_window) + 1:
            raise VolumeIntelligenceError(
                f"Insufficient data for volume intelligence: {symbol} has {len(df)} bars"
            )

        close = df["close"].astype(float)
        volume = df["volume"].astype(float)
        timestamp = pd.Timestamp(df.index[-1])

        latest_volume = float(volume.iloc[-1])
        avg_volume = float(volume.tail(config.spike_lookback).mean())
        volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 0.0

        returns = close.pct_change().fillna(0.0)
        vw_mom_series = (returns * (volume / max(avg_volume, 1e-9))).rolling(
            config.vw_momentum_window,
            min_periods=config.vw_momentum_window,
        ).sum()
        vw_momentum = float(vw_mom_series.iloc[-1]) if pd.notna(vw_mom_series.iloc[-1]) else 0.0

        signals: list[VolumeSignal] = []

        if volume_ratio >= config.spike_multiple_threshold:
            signals.append(
                VolumeSignal(
                    symbol=symbol,
                    signal_type=VolumeSignalType.SPIKE,
                    strength=volume_ratio,
                    timestamp=timestamp,
                    reason=(
                        f"latest volume {latest_volume:.0f} is {volume_ratio:.2f}x "
                        f"the {config.spike_lookback}-bar average"
                    ),
                )
            )

        acc_strength, dist_strength = self._acc_dist_strength(
            close=close,
            volume=volume,
            window=max(config.accumulation_window, config.distribution_window),
        )

        if acc_strength >= config.accumulation_strength_threshold:
            signals.append(
                VolumeSignal(
                    symbol=symbol,
                    signal_type=VolumeSignalType.ACCUMULATION,
                    strength=acc_strength,
                    timestamp=timestamp,
                    reason=f"up-volume/down-volume ratio {acc_strength:.2f} indicates accumulation",
                )
            )

        if dist_strength >= config.distribution_strength_threshold:
            signals.append(
                VolumeSignal(
                    symbol=symbol,
                    signal_type=VolumeSignalType.DISTRIBUTION,
                    strength=dist_strength,
                    timestamp=timestamp,
                    reason=f"down-volume/up-volume ratio {dist_strength:.2f} indicates distribution",
                )
            )

        if vw_momentum != 0.0:
            signals.append(
                VolumeSignal(
                    symbol=symbol,
                    signal_type=VolumeSignalType.VW_MOMENTUM,
                    strength=abs(vw_momentum),
                    timestamp=timestamp,
                    reason=f"volume-weighted momentum {vw_momentum:.4f}",
                    metadata={"direction": "positive" if vw_momentum > 0 else "negative"},
                )
            )

        metrics = {
            "latest_volume": latest_volume,
            "avg_volume": avg_volume,
            "volume_ratio": volume_ratio,
            "accumulation_strength": acc_strength,
            "distribution_strength": dist_strength,
            "vw_momentum": vw_momentum,
        }

        return VolumeAnalysisSnapshot(
            symbol=symbol,
            timeframe=config.timeframe,
            timestamp=timestamp,
            signals=signals,
            metrics=metrics,
        )

    def analyze_many(
        self,
        data_by_symbol: dict[str, DataHandler],
        config: VolumeIntelligenceConfig,
    ) -> list[VolumeAnalysisSnapshot]:
        out: list[VolumeAnalysisSnapshot] = []
        for symbol, dh in data_by_symbol.items():
            try:
                out.append(self.analyze_symbol(symbol, dh, config))
            except Exception:
                continue
        return out

    @staticmethod
    def _acc_dist_strength(close: pd.Series, volume: pd.Series, window: int) -> tuple[float, float]:
        ret = close.pct_change().fillna(0.0).tail(window)
        vol = volume.tail(window)

        up_volume = float(vol[ret > 0].sum())
        down_volume = float(vol[ret < 0].sum())

        acc_strength = (up_volume / down_volume) if down_volume > 0 else (up_volume if up_volume > 0 else 0.0)
        dist_strength = (down_volume / up_volume) if up_volume > 0 else (down_volume if down_volume > 0 else 0.0)

        return acc_strength, dist_strength
