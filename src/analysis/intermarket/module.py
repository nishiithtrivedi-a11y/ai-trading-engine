"""
Intermarket analysis module.

Derives cross-asset context features from normalized intermarket payloads and
existing market/macro context.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analysis.base import BaseAnalysisModule
from src.data.intermarket_sources import IntermarketDataBundle, normalize_intermarket_payload


def _aligned_corr(lhs: pd.Series, rhs: pd.Series) -> float | None:
    if lhs.empty or rhs.empty:
        return None
    merged = pd.concat([lhs, rhs], axis=1, join="inner").dropna()
    if len(merged) < 8:
        return None
    corr = merged.iloc[:, 0].corr(merged.iloc[:, 1])
    if pd.isna(corr):
        return None
    return float(corr)


def _last_return(data: pd.DataFrame) -> float | None:
    if data is None or data.empty or "close" not in data.columns or len(data) < 2:
        return None
    prev = float(data["close"].iloc[-2])
    curr = float(data["close"].iloc[-1])
    if prev == 0:
        return None
    return float((curr - prev) / prev)


class IntermarketAnalysisModule(BaseAnalysisModule):
    """Intermarket module: divergence, correlations, confirmation/contradiction."""

    name: str = "intermarket"
    version: str = "1.0.0"

    def is_enabled(self, config=None) -> bool:
        return True

    def supports(self, instrument_type: str, timeframe: str) -> bool:
        return True

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        bundle = self._resolve_bundle(context)
        metadata = dict(bundle.provider_metadata)

        features: dict[str, Any] = {
            "intermarket_available": 1.0 if metadata.get("available") else 0.0,
            "intermarket_degraded": 1.0 if metadata.get("degraded") else 0.0,
            "intermarket_provider": metadata.get("provider", "derived"),
            "intermarket_series_count": float(metadata.get("series_count", 0) or 0),
            "intermarket_scalar_count": float(metadata.get("scalar_count", 0) or 0),
        }

        asset_returns = bundle.series.get("asset_returns")
        if asset_returns is None:
            asset_returns = self._asset_return_series(data)

        benchmark_returns = bundle.series.get("benchmark_returns", pd.Series(dtype="float64"))
        sector_returns = bundle.series.get("sector_returns", pd.Series(dtype="float64"))
        rates_returns = bundle.series.get("rates_returns", pd.Series(dtype="float64"))
        usd_returns = bundle.series.get("usd_returns", pd.Series(dtype="float64"))
        commodity_returns = bundle.series.get("commodity_returns", pd.Series(dtype="float64"))
        inr_returns = bundle.series.get("inr_returns", pd.Series(dtype="float64"))

        corr_asset_benchmark = _aligned_corr(asset_returns, benchmark_returns)
        corr_asset_sector = _aligned_corr(asset_returns, sector_returns)
        corr_asset_rates = _aligned_corr(asset_returns, rates_returns)
        corr_usd_commodity = _aligned_corr(usd_returns, commodity_returns)
        corr_inr_commodity = _aligned_corr(inr_returns, commodity_returns)

        features["intermarket_corr_asset_benchmark"] = corr_asset_benchmark
        features["intermarket_corr_asset_sector"] = corr_asset_sector
        features["intermarket_corr_asset_rates"] = corr_asset_rates
        features["intermarket_corr_usd_commodity"] = corr_usd_commodity
        features["intermarket_corr_inr_commodity"] = corr_inr_commodity

        asset_last = _last_return(data)
        benchmark_last = self._series_last(benchmark_returns)
        sector_last = self._series_last(sector_returns)
        rates_last = self._series_last(rates_returns)

        divergence = None
        if asset_last is not None and benchmark_last is not None:
            divergence = float(asset_last - benchmark_last)
        features["intermarket_index_sector_divergence"] = divergence

        confirmation = 0.0
        contradiction = 0.0
        if asset_last is not None:
            # In simple equity context, rising asset + falling rates is supportive,
            # while rising asset + rising rates may be contradictory.
            if rates_last is not None:
                if asset_last > 0 and rates_last < 0:
                    confirmation += 1.0
                if asset_last > 0 and rates_last > 0:
                    contradiction += 1.0
            if benchmark_last is not None:
                if asset_last * benchmark_last > 0:
                    confirmation += 1.0
                else:
                    contradiction += 1.0
            if sector_last is not None:
                if asset_last * sector_last > 0:
                    confirmation += 1.0
                else:
                    contradiction += 1.0

        features["intermarket_confirmation_score"] = confirmation
        features["intermarket_contradiction_score"] = contradiction
        features["intermarket_confirmation_flag"] = 1.0 if confirmation > contradiction else 0.0
        features["intermarket_contradiction_flag"] = 1.0 if contradiction > confirmation else 0.0

        features["intermarket_equity_rates_context"] = self._signed_context(corr_asset_rates)
        features["intermarket_usd_commodity_context"] = self._signed_context(corr_usd_commodity)
        features["intermarket_inr_commodity_context"] = self._signed_context(corr_inr_commodity)

        coverage_count = sum(
            1 for value in [
                corr_asset_benchmark,
                corr_asset_sector,
                corr_asset_rates,
                corr_usd_commodity,
                corr_inr_commodity,
            ] if value is not None
        )
        features["intermarket_coverage"] = float(coverage_count)

        return features

    @staticmethod
    def _resolve_bundle(context: dict) -> IntermarketDataBundle:
        existing = context.get("intermarket_data")
        if isinstance(existing, IntermarketDataBundle):
            return existing

        provider = str(
            context.get("intermarket_provider")
            or context.get("analysis_provider_selection", {}).get("intermarket", "derived")
        ).strip().lower() or "derived"

        payload = context.get("intermarket_payload")
        if payload is None and isinstance(existing, dict):
            payload = existing
        return normalize_intermarket_payload(provider, payload)

    @staticmethod
    def _asset_return_series(data: pd.DataFrame) -> pd.Series:
        if data is None or data.empty or "close" not in data.columns:
            return pd.Series(dtype="float64")
        close = pd.to_numeric(data["close"], errors="coerce").dropna()
        returns = close.pct_change().dropna()
        if returns.empty:
            return pd.Series(dtype="float64")
        return returns

    @staticmethod
    def _series_last(series: pd.Series) -> float | None:
        if series is None or series.empty:
            return None
        value = float(series.iloc[-1])
        if pd.isna(value):
            return None
        return value

    @staticmethod
    def _signed_context(value: float | None) -> float:
        if value is None:
            return 0.0
        if value > 0.2:
            return 1.0
        if value < -0.2:
            return -1.0
        return 0.0

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Intermarket context module with cross-asset correlation and confirmation flags.",
        }
