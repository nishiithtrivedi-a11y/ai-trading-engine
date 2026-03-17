"""
Quantitative Analysis Module.

Computes statistical / quantitative features from price returns.

Features produced
-----------------
volatility_5d         : Annualised 5-day rolling return std (float | None)
volatility_20d        : Annualised 20-day rolling return std (float | None)
volatility_60d        : Annualised 60-day rolling return std (float | None)
momentum_5d           : 5-bar price return (pct) (float | None)
momentum_20d          : 20-bar price return (pct) (float | None)
momentum_60d          : 60-bar price return (pct) (float | None)
return_zscore_20d     : Z-score of latest 1-bar return vs 20-bar window (float | None)
sharpe_20d            : Rolling 20-day Sharpe (annualised, rf=0) (float | None)
volume_zscore_20d     : Z-score of latest volume vs 20-bar average (float | None)
"""

from __future__ import annotations

import math

import pandas as pd

from src.analysis.base import BaseAnalysisModule

_ANNUALISE = math.sqrt(252)


class QuantAnalysisModule(BaseAnalysisModule):
    """Quantitative / statistical analysis module."""

    name: str = "quant"
    version: str = "1.0.0"

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        """Compute return-based statistical features."""
        if data is None or data.empty or "close" not in data.columns:
            return {}

        close = data["close"]
        returns = close.pct_change().dropna()
        features: dict = {}

        # Rolling volatility and momentum for each lookback
        for n in (5, 20, 60):
            if len(returns) >= n:
                vol = returns.rolling(n).std().iloc[-1]
                features[f"volatility_{n}d"] = (
                    float(vol * _ANNUALISE) if not pd.isna(vol) else None
                )
                mom = close.pct_change(n).iloc[-1]
                features[f"momentum_{n}d"] = float(mom) if not pd.isna(mom) else None

        # Z-score of latest 1-bar return vs 20-bar distribution
        if len(returns) >= 20:
            mu = returns.rolling(20).mean().iloc[-1]
            sigma = returns.rolling(20).std().iloc[-1]
            if not pd.isna(mu) and not pd.isna(sigma) and sigma > 1e-12:
                features["return_zscore_20d"] = float(
                    (returns.iloc[-1] - mu) / sigma
                )
            else:
                features["return_zscore_20d"] = None

        # Rolling 20-day Sharpe (annualised, risk-free = 0)
        if len(returns) >= 20:
            rolling_mu = returns.rolling(20).mean().iloc[-1]
            rolling_sigma = returns.rolling(20).std().iloc[-1]
            if (
                not pd.isna(rolling_mu)
                and not pd.isna(rolling_sigma)
                and rolling_sigma > 1e-12
            ):
                features["sharpe_20d"] = float(
                    (rolling_mu / rolling_sigma) * _ANNUALISE
                )
            else:
                features["sharpe_20d"] = None

        # Volume z-score
        if "volume" in data.columns and len(data) >= 20:
            vol_series = data["volume"].astype(float)
            vol_mu = vol_series.rolling(20).mean().iloc[-1]
            vol_sigma = vol_series.rolling(20).std().iloc[-1]
            latest_vol = float(vol_series.iloc[-1])
            if (
                not pd.isna(vol_mu)
                and not pd.isna(vol_sigma)
                and vol_sigma > 1e-12
            ):
                features["volume_zscore_20d"] = (latest_vol - float(vol_mu)) / float(vol_sigma)
            else:
                features["volume_zscore_20d"] = None

        return features

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Return-based volatility, momentum, and z-score features",
        }
